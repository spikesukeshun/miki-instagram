"""投稿を生成するこの作業ディレクトリが、確定済みルールを満たしているか確認する。

2026-08-08 に判明した問題：このディレクトリの main は 2026-04-26 以降 origin/main と
分岐したまま同期されておらず、5〜8月に origin/main へ入った修正
（シートI列以降の廃止・listの番号の左揃え）が、実際に画像を作るマシンに届いていなかった。
その結果、文章としては確定していたルールが投稿の上で巻き戻った。

このスクリプトは2種類のチェックを行う：

1. 恒久ルールの実装チェック（ネットワーク不要・これが本体）
   コードが確定済みルールどおりになっているかをソースから直接検証する。
   git の状態がどうであれ、ここが通れば投稿は正しく作られる。

2. origin/main との差分レポート（git fetch できるときのみ・参考情報）
   生成系スクリプトについて、origin/main にあってこちらに無いコミットを一覧する。

Usage:
    python3 check_repo_sync.py            # 両方
    python3 check_repo_sync.py --no-fetch # 1 のみ（オフライン）

終了コード: 0=問題なし / 1=恒久ルール違反あり（投稿を作ってはいけない）
"""
import argparse
import ast
import os
import re
import subprocess
import sys

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# origin/main との差分を見る対象（投稿の中身に直接影響するもの）
GENERATION_SCRIPTS = [
    "create_post.py",
    "generate_carousel.py",
    "register_post.py",
    "review_post.py",
    "check_week_slots.py",
]


def _read(name: str) -> str:
    with open(os.path.join(REPO_DIR, name), encoding="utf-8") as f:
        return f.read()


def check_list_left_align() -> tuple[bool, str]:
    """listスライドの番号付き箇条書きが左揃えになっているか。

    行ごとに中央寄せ（ループ内で x を計算し直す）に戻っていないことを見る。
    """
    src = _read("generate_carousel.py")
    m = re.search(r"def generate_list_slide\(.*?\n(.*?)\ndef ", src, re.S)
    if not m:
        return False, "generate_list_slide() が見つかりません"
    body = m.group(1)
    loop = body.split("for ", 1)[-1] if "for " in body else ""
    # 描画ループの中で x を計算し直していたら行ごと中央寄せ＝ルール違反
    if re.search(r"x\s*=\s*\(W\s*-\s*total\)\s*//\s*2", body):
        return False, ("listの番号が行ごとの中央寄せに戻っています— 左揃え（全項目で同じx）に"
                       "してください。CLAUDE.md「維持されるルール」参照")
    if "item_x" not in body:
        return False, "listの番号・本文が共通のx座標で描画されていません（左揃えの実装が無い）"
    return True, "listの番号付き箇条書きは左揃え ✓"


def check_sheet_columns() -> tuple[bool, str]:
    """シート書き込みが A〜H の8列に収まっているか。"""
    src = _read("register_post.py")
    wide = sorted(set(re.findall(r'f"A\{[^}]+\}:([I-Z])\{', src)))
    if wide:
        return False, (f"register_post.py が A〜{wide[-1]} 列に書き込んでいます— "
                       f"シートは A〜H の8列のみ（I列以降は2026-07-11に廃止）")
    if "SHEET_LAST_COL" not in src:
        return False, "register_post.py に SHEET_LAST_COL がありません（列範囲が固定されていない）"
    create_src = _read("create_post.py")
    m = re.search(r"register\(\s*(.*?)\)\s*\n", create_src, re.S)
    if m and ("alt_text=" in m.group(1) or "seed=" in m.group(1)):
        return False, "create_post.py が register() に seed / alt_text を渡しています— シートI列以降が復活します"
    return True, "シート書き込みは A〜H の8列 ✓"


def _literal_constant(src: str, name: str):
    """ソースを AST で読んで、モジュール直下の定数 name の値を返す（無ければ None）。

    文字列マッチだと「クォートの種類を変えた」「要素の順番を入れ替えた」だけで
    チェックが外れ、ルールは守られているのに ❌ になる（＝投稿フローが止まる）。
    実行はせず構文木だけ見るので、依存パッケージが無い環境でも動く。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = node.value
                # frozenset({...}) / set([...]) のように包んであっても中身を取り出す
                if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                        and value.func.id in ("frozenset", "set", "tuple", "list")
                        and len(value.args) == 1):
                    value = value.args[0]
                try:
                    return ast.literal_eval(value)
                except ValueError:
                    return None
    return None


def _bg_prompt_defaults(src: str) -> list[str]:
    """`....get("bg_prompt", <既定値>)` の既定値を AST で拾う。

    空文字の既定値（`slide.get("bg_prompt", "")`）は「無ければ空」というだけで
    ルール違反のプロンプトを作らないので対象外にする。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and len(node.args) == 2):
            continue
        key = node.args[0]
        if not (isinstance(key, ast.Constant) and key.value == "bg_prompt"):
            continue
        try:
            default = ast.literal_eval(node.args[1])
        except ValueError:
            continue
        if isinstance(default, str) and default.strip():
            found.append(default)
    return found


def check_no_silent_bg_fallback() -> tuple[bool, str]:
    """Drive指定の失敗時に、黙ってAI生成や別画像へフォールバックしないこと。"""
    src = _read("create_post.py")
    if "Drive画像の取得失敗、HFで代替生成" in src:
        return False, ("create_post.py がDrive取得失敗時に黙ってAI生成へフォールバックします— "
                       "意図しない生成画像の使用につながるため例外で止めること")
    # 文字列マッチではなく AST で定数の中身を見る（クォート・順序・型を変えても通る）
    keys = _literal_constant(src, "REQUIRED_DRIVE_REUSE_KEYS")
    if keys is None or set(keys) != {"reuse_source", "reuse_theme", "reuse_filename"}:
        return False, ("create_post.py の REQUIRED_DRIVE_REUSE_KEYS が"
                       "（reuse_source / reuse_theme / reuse_filename）ではありません"
                       f"（現在: {keys}）")
    if "_validate_reuse_fields" not in src:
        return False, "create_post.py に _validate_reuse_fields()（3点セットの欠落チェック）がありません"
    # Drive分岐の中に reuse_index が現れたら、番号による暗黙フォールバックが復活している
    drive_branch = re.search(r"# --- Drive 画像を使用 ---(.*?)# --- ローカルファイル", src, re.S)
    if not drive_branch:
        return False, "create_post.py の Drive 分岐が見つかりません（構造が変わっています）"
    # コメントは対象外（「reuse_index は使わない」という説明で誤検知しないように）
    drive_code = "\n".join(re.sub(r"#.*$", "", line) for line in drive_branch.group(1).splitlines())
    if "reuse_index" in drive_code:
        return False, ("create_post.py の Drive 分岐が reuse_index を使っています— "
                       "ファイル名ではなく番号で画像を選ぶと、指定漏れが0番目の画像で"
                       "黙って埋まる（意図しない写真で投稿が完成する）")
    return True, "Drive取得失敗時にAI生成・別画像へ落ちない ✓"


def check_bg_prompt_no_default() -> tuple[bool, str]:
    """bg_prompt の書き忘れをルール違反のデフォルトで埋めないこと。"""
    src = _read("create_post.py")
    if "def validate_bg_prompt" not in src:
        return False, "create_post.py に validate_bg_prompt() がありません（bg_prompt の検証が無い）"
    # 中身のある既定値だけを違反とする（`slide.get("bg_prompt", "")` は無害なので通す）
    defaults = _bg_prompt_defaults(src)
    if defaults:
        return False, (f"create_post.py が bg_prompt にデフォルト値を持っています（{defaults[0]}）— "
                       "省略はデフォルトで埋めず ValueError で止めること"
                       "（旧デフォルト soft pink がピンク禁止違反を静かに通していた）")
    return True, "bg_prompt は既定値で埋めず検証して止める ✓"


def check_generate_guard() -> tuple[bool, str]:
    """review_post.py が AI生成の暗黙採用を止められること。"""
    src = _read("review_post.py")
    if "check_backgrounds" not in src or "bg_generate_reason" not in src:
        return False, "review_post.py に背景チェック（check_backgrounds）がありません"
    return True, "review_post.py の背景チェックあり ✓"


def _is_compared_against(src: str, name: str) -> bool:
    """定数 name が実際に比較（==/!=）に使われているかを AST で見る。

    出現回数を数えるだけだと、エラーメッセージの f-string に名前が残っている
    かぎり ✓ になり、肝心の比較行が消えていても気づけない。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for side in [node.left, *node.comparators]:
            if isinstance(side, ast.Name) and side.id == name:
                return True
    return False


def check_cta_subtitle_rule() -> tuple[bool, str]:
    """CTAスライドの subtitle 固定文言チェックが生きていること（恒久・2026-09-06）。

    subtitle は LP（プロフィールのリンク先）への唯一の導線なので、
    回ごとに言い回しが変わると「どこを見ればいいか」が毎回ぶれる。
    review_post.py が完全一致で止める実装になっているかを見る。
    """
    src = _read("review_post.py")
    value = _literal_constant(src, "CTA_REQUIRED_SUBTITLE")
    if value is None:
        return False, ("review_post.py に CTA_REQUIRED_SUBTITLE がありません— "
                       "CTAスライドの subtitle は毎回同じ固定文言にする恒久ルール")
    if "プロフィール" not in value or "リンク" not in value:
        return False, (f"CTA_REQUIRED_SUBTITLE に LP誘導（プロフィール／リンク）がありません"
                       f"（現在: {value!r}）")
    if not _is_compared_against(src, "CTA_REQUIRED_SUBTITLE"):
        return False, ("CTA_REQUIRED_SUBTITLE が照合に使われていません— "
                       "定義とエラーメッセージだけ残って比較が消えると、"
                       "固定文言が黙って変わる")
    return True, "CTAスライドの subtitle は固定文言で照合 ✓"


def _function_source(src: str, name: str) -> str:
    """モジュール内の関数 name の本体ソースだけを返す（無ければ ""）。

    "ファイルを def で split して以降全部" だと、別の関数に同じ字面があるだけで
    素通りする。関数の範囲を構文木で確定させてから中を見る。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            end = getattr(node, "end_lineno", None) or len(lines)
            return "\n".join(lines[node.lineno - 1:end])
    return ""


def _dict_string_keys(src: str, var_name: str) -> set:
    """モジュール内で var_name に代入されている辞書の、文字列キーを返す。

    正規表現でインデントごと当てにいくと、辞書を別の場所へ移しただけで
    「構造が変わっています」と誤検知して投稿フロー全体が止まる。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == var_name for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        return {k.value for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()


def _strip_comments(code: str) -> str:
    return "\n".join(re.sub(r"#.*$", "", line) for line in code.splitlines())


def _compares_last_slide_to_cta(src: str, func_name: str) -> bool:
    """関数 func_name の中に「最後のスライドの型を "cta" と比べる比較式」が実在するか。

    関数内に "cta" という字面があるだけでは足りない（check_slides には
    CTA固定文言チェックなど別の "cta" がいくつもあり、比較を消しても素通りした）。
    slides[-1] から取った値（またはそれを入れた変数）と "cta" を比べる
    Compare ノードを構文木で探す。書き方（!= / not in ("cta",)）には左右されない。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    for fn in ast.walk(tree):
        if not (isinstance(fn, ast.FunctionDef) and fn.name == func_name):
            continue
        names = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and "slides[-1]" in ast.unparse(node.value):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            left = ast.unparse(node.left)
            if left not in names and "slides[-1]" not in left:
                continue
            for comp in node.comparators:
                if any(isinstance(c, ast.Constant) and c.value == "cta"
                       for c in ast.walk(comp)):
                    return True
    return False


def check_post_style_cta_last() -> tuple[bool, str]:
    """flipbook / phrase の末尾が CTA スライドであること（恒久・2026-09-21）。

    この2形式は末尾固定2枚（slide8 / slide7）を付けない。CTAスライドが
    消えると review_post.py の CTA固定文言チェックも check_lp_guidance() も
    見る対象を失い、予約導線が黙って無くなる。
    画像を作る前に止まる create_post.py 側と、校閲する review_post.py 側の
    両方に検査が生きているかを見る。
    """
    cp = _read("create_post.py")
    rp = _read("review_post.py")

    if "NO_FOOTER_POST_STYLES" not in rp:
        return False, ("review_post.py に NO_FOOTER_POST_STYLES がありません— "
                       "flipbook / phrase で末尾固定2枚を抑止する恒久ルール")

    # create_post.py: 末尾が cta でなければ例外
    if "resolve_post_style" not in cp:
        return False, ("create_post.py に resolve_post_style() がありません— "
                       "枚数と末尾CTAは画像を作る前に止める恒久ルール")
    if not _compares_last_slide_to_cta(cp, "resolve_post_style"):
        return False, ("create_post.py の resolve_post_style() で末尾CTAを"
                       "照合していません— CTAが消えると予約導線が黙って無くなる")

    # 固定2枚の追加が「抑止する側」で書かれているか
    # （standard のときだけ追加、にすると未知の値で固定2枚が落ちる）
    # コメントの中の字面で通ってしまわないよう、run() のコードだけを見る
    if "post_style in NO_FOOTER_POST_STYLES" not in _strip_comments(_function_source(cp, "run")):
        return False, ("create_post.py の末尾2枚の自動追加が "
                       "NO_FOOTER_POST_STYLES での抑止になっていません— "
                       "未知の post_style で固定2枚が黙って落ちる")

    # review 側も「最後のスライドの型を cta と比べている」ことまで見る。
    # 関数の範囲は構文木で確定させる（ファイル末尾まで見ると、
    # 別の関数にある同じ字面で素通りしてしまう）。
    if not _compares_last_slide_to_cta(rp, "check_slides"):
        return False, ("review_post.py の check_slides() が末尾のCTAを照合していません— "
                       "定義だけ残って比較が消えると、CTA無しの投稿が校閲を通る")

    return True, "flipbook / phrase の末尾CTAは create_post と review_post の両方で照合 ✓"


def check_slide_type_allowlist() -> tuple[bool, str]:
    """review_post.py の型 allowlist が generate_carousel.py と一致すること（恒久・2026-09-21）。

    generate_carousel.py は generators[slide["type"]] の直接添字なので、
    未知の型は KeyError になるまで気づけない。review_post.py の
    VALID_SLIDE_TYPES で校閲時に止める運用にしているが、片方だけ型を
    足すと「描けるのに校閲で ❌」「校閲を通るのに KeyError」のどちらかになる。
    """
    rp = _read("review_post.py")
    gc = _read("generate_carousel.py")

    allowed = _literal_constant(rp, "VALID_SLIDE_TYPES")
    if allowed is None:
        return False, ("review_post.py に VALID_SLIDE_TYPES がありません— "
                       "未知の型を校閲で止める恒久ルール")
    allowed = set(allowed)

    registered = _dict_string_keys(gc, "generators")
    if not registered:
        return False, ("generate_carousel.py の generators 辞書が見つかりません"
                       "（構造が変わっています）")

    if allowed != registered:
        missing = registered - allowed
        extra = allowed - registered
        detail = []
        if missing:
            detail.append(f"描けるのに校閲が知らない型: {' / '.join(sorted(missing))}")
        if extra:
            detail.append(f"校閲は許すのに描けない型: {' / '.join(sorted(extra))}")
        return False, ("VALID_SLIDE_TYPES と generate_carousel.py の generators が"
                       "一致しません— " + " / ".join(detail))
    return True, f"スライド型の allowlist は generators と一致（{len(allowed)}種）✓"


def check_no_silent_local_fallback() -> tuple[bool, str]:
    """bg_strategy: "local" でファイルが無い時、AI生成へ落ちずに止まること（恒久・2026-09-23）。

    以前は local_path が見つからないと HF 生成へ黙って落ち、指定した写真の
    代わりにAI画像で投稿が完成していた。案B（flipbook）は全スライドが local なので、
    これが復活するとパラパラ漫画のコマが全部AI画像に置き換わる。
    """
    cp = _read("create_post.py")
    m = re.search(r"# --- ローカルファイル(.*?)# --- Instagram", cp, re.S)
    if not m:
        return False, "create_post.py の local 分岐が見つかりません（構造が変わっています）"
    code = _strip_comments(m.group(1))
    if "raise ValueError" not in code:
        return False, ("create_post.py の local 分岐が、ファイルが無い時に止まりません— "
                       "指定した写真の代わりにAI画像で投稿が完成する")
    if "HFで代替生成" in code:
        return False, "create_post.py の local 分岐に HF 生成へのフォールバックが残っています"
    return True, "local の背景が無い時にAI生成へ落ちない ✓"


def check_graph_api_host() -> tuple[bool, str]:
    """Meta Graph API のホストが全スクリプトで揃っていること（恒久・2026-09-23）。

    INSTAGRAM_ACCESS_TOKEN は Facebook 発行のトークンで、graph.instagram.com
    では解析できない（"Invalid OAuth access token - Cannot parse access token"）。
    create_post.py だけが graph.instagram.com を向いていたため、過去投稿の取得と
    カルーセル子画像の取得が常に失敗し、reuse_source: "instagram" の経路が
    丸ごと死んでいた（現在の運用が Drive 写真なので長く気づかれなかった）。

    ホストの定数は6ファイルに散っている。1か所にまとめるには稼働中のスクリプトを
    広く触ることになるので、「値の重複は許し、ずれたらここで止める」方式にする。
    """
    hosts = {}
    for name in sorted(os.listdir(REPO_DIR)):
        if not name.endswith(".py"):
            continue
        try:
            src = _read(name)
        except OSError:
            continue
        for host in set(re.findall(r"https://graph\.(?:facebook|instagram)\.com", src)):
            hosts.setdefault(host, []).append(name)
    if not hosts:
        return False, "Meta Graph API のホストがどこにも見つかりません（構造が変わっています）"
    if len(hosts) > 1:
        detail = " / ".join(f"{h} → {', '.join(f)}" for h, f in sorted(hosts.items()))
        return False, ("Meta Graph API のホストが揃っていません— " + detail +
                       "。INSTAGRAM_ACCESS_TOKEN は graph.facebook.com でしか解析できない")
    host = next(iter(hosts))
    if "instagram" in host:
        return False, (f"Meta Graph API のホストが {host} になっています— "
                       f"Facebook発行のトークンでは解析できません")
    return True, f"Meta Graph API のホストは全スクリプトで統一（{host}）✓"


SHADOW_ALLOWED_FUNCS = {"_mosaic_tile"}


def _param_names(fn) -> list:
    a = fn.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]


def check_text_shadow_only_in_tile() -> tuple[bool, str]:
    """文字のシャドウは mosaic の tile だけ（恒久・2026-09-27）。

    「テキストのシャドウは全てなし」（rules/carousel-design.md）の唯一の例外が
    mosaic の区画の文字（ユーザー指定・2026-09-23）。例外が他の型に広がると、
    案A・案Bの他の型にも影が戻る。generate_carousel.py を AST で見て、次を止める:
      - 影色の定数 MOSAIC_SHADOW_RGB を tile 以外（モジュール直下も含む）で参照する
      - shadow 引数の既定値を None 以外にする（呼び出し側すべてに影が付く）
      - shadow を渡す呼び出し（キーワードでも位置引数でも）。ただし None と、
        その関数自身が受け取った shadow 引数をそのまま下へ渡す中継は除く
    手書きの二度描き（ずらして暗い色で描いてから白で描く）は見分けられない。
    """
    tree = ast.parse(_read("generate_carousel.py"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    # shadow を引数に持つ関数と、その位置（位置引数で渡された時に気づくため）
    shadow_pos = {}
    offenders = []
    for fn in funcs:
        a = fn.args
        positional = [x.arg for x in a.posonlyargs + a.args]
        if "shadow" in positional:
            shadow_pos[fn.name] = positional.index("shadow")
            defaults = dict(zip(positional[len(positional) - len(a.defaults):], a.defaults))
            d = defaults.get("shadow")
        else:
            kw = dict(zip([x.arg for x in a.kwonlyargs], a.kw_defaults))
            d = kw.get("shadow", ast.Constant(None)) if "shadow" in kw else None
        if d is not None and not (isinstance(d, ast.Constant) and d.value is None):
            offenders.append(f"{fn.name}（shadow の既定値）")

    for fn in funcs:
        if fn.name in SHADOW_ALLOWED_FUNCS:
            continue
        own = set(_param_names(fn))
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and node.id == "MOSAIC_SHADOW_RGB":
                offenders.append(fn.name)
            elif isinstance(node, ast.Call):
                callee = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if callee in shadow_pos and len(node.args) > shadow_pos[callee]:
                    offenders.append(f"{fn.name}（{callee} に位置引数で shadow）")
                for kw in node.keywords:
                    if kw.arg != "shadow":
                        continue
                    v = kw.value
                    if isinstance(v, ast.Constant) and v.value is None:
                        continue
                    # 受け取った shadow をそのまま下へ渡すだけの中継
                    # （draw_multiline_centered → draw_centered）は影を足していない
                    if isinstance(v, ast.Name) and v.id == "shadow" and "shadow" in own:
                        continue
                    offenders.append(fn.name)

    # モジュール直下（別名への代入など）での参照。定義そのものは除く
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        targets = stmt.targets if isinstance(stmt, ast.Assign) else []
        if any(isinstance(tg, ast.Name) and tg.id == "MOSAIC_SHADOW_RGB" for tg in targets):
            continue
        if any(isinstance(n, ast.Name) and n.id == "MOSAIC_SHADOW_RGB" for n in ast.walk(stmt)):
            offenders.append(f"モジュール直下 {stmt.lineno}行目")

    if offenders:
        return False, (f"文字のシャドウが mosaic の tile 以外で使われています: "
                       f"{', '.join(sorted(set(offenders)))}— シャドウ禁止の恒久ルール")
    return True, "文字のシャドウは mosaic の tile だけ ✓"


RULE_CHECKS = [
    check_list_left_align,
    check_sheet_columns,
    check_no_silent_bg_fallback,
    check_bg_prompt_no_default,
    check_generate_guard,
    check_cta_subtitle_rule,
    check_post_style_cta_last,
    check_slide_type_allowlist,
    check_no_silent_local_fallback,
    check_graph_api_host,
    check_text_shadow_only_in_tile,
]


def report_origin_diff() -> None:
    """origin/main にあってこちらに無いコミットを生成系スクリプト単位で出す（参考情報）。"""
    try:
        subprocess.run(["git", "fetch", "--quiet", "origin", "main"],
                       cwd=REPO_DIR, check=True, timeout=60)
    except Exception as e:
        print(f"\n[参考] origin/main を取得できませんでした（{e}）— 差分レポートはスキップします")
        return

    print("\n--- origin/main との差分（生成系スクリプト） ---")
    any_behind = False
    for path in GENERATION_SCRIPTS:
        try:
            # --full-history を付けないと、マージを含む履歴でコミットが隠れる
            out = subprocess.check_output(
                ["git", "log", "--full-history", "--oneline", "HEAD..origin/main", "--", path],
                cwd=REPO_DIR, text=True, timeout=60,
            ).strip()
        except Exception as e:
            print(f"  {path}: 確認できませんでした（{e}）")
            continue
        if out:
            any_behind = True
            lines = out.splitlines()
            print(f"  ⚠ {path}: origin/main に未取り込みのコミット {len(lines)}件")
            for line in lines[:5]:
                print(f"      {line}")
            if len(lines) > 5:
                print(f"      … 他{len(lines) - 5}件")
        else:
            print(f"  ✓ {path}: origin/main と同期済み")

    if any_behind:
        print("\n  ※ 上のルールチェックが全て ✓ なら投稿を作って問題ない。")
        print("    ただし origin/main 側の修正が届いていないので、時間のあるときに")
        print("    取り込みを検討すること（GitHub Actions の投稿処理は origin/main を使う）。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="投稿生成環境の恒久ルール実装チェック")
    parser.add_argument("--no-fetch", action="store_true", help="origin/main との差分レポートを行わない")
    args = parser.parse_args()

    print("=" * 50)
    print("🔧 投稿生成環境チェック")
    print("=" * 50)

    failures = []
    for check in RULE_CHECKS:
        ok, msg = check()
        print(f"  {'✓' if ok else '✗'} {msg}")
        if not ok:
            failures.append(msg)

    if not args.no_fetch:
        report_origin_diff()

    print("=" * 50)
    if failures:
        print(f"\n❌ 恒久ルール違反 {len(failures)}件— 投稿を作る前に直してください\n")
        sys.exit(1)
    print("\n✅ 恒久ルールはすべて実装されています\n")
    sys.exit(0)
