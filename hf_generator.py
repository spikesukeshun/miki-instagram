"""
Hugging Face FLUX.1-schnell を使った背景画像生成モジュール
Pollinations.ai の代替。seed対応・プロンプト学習機能付き。
"""
import json
import os
import random
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image

HF_API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
FALLBACK_API_URL = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"
PROMPT_HISTORY_PATH = "prompt_history.json"
BACKGROUNDS_DIR = "backgrounds"

# 品質向上サフィックス（エステ・サロン系に特化）
BASE_QUALITY_SUFFIX = (
    ", soft natural lighting, elegant interior, luxury spa atmosphere, "
    "professional photography, 4k resolution, no text, no watermark, "
    "shallow depth of field, warm tones, high quality"
)


def load_prompt_history() -> dict:
    if os.path.exists(PROMPT_HISTORY_PATH):
        with open(PROMPT_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"bad_patterns": [], "entries": []}


def save_prompt_entry(
    theme: str,
    slide_type: str,
    prompt: str,
    seed: int,
    quality: str = "unknown",
    notes: str = "",
) -> None:
    """プロンプト生成結果を prompt_history.json に追記"""
    history = load_prompt_history()
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "theme": theme,
        "slide_type": slide_type,
        "prompt": prompt,
        "seed": seed,
        "quality": quality,
        "notes": notes,
    }
    history["entries"].append(entry)
    with open(PROMPT_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _build_full_prompt(base_prompt: str) -> str:
    """悪例パターンを回避した最終プロンプトを構築"""
    history = load_prompt_history()
    bad_patterns = history.get("bad_patterns", [])

    prompt = base_prompt + BASE_QUALITY_SUFFIX

    # 悪例パターンが記録されていれば回避指示を追加（上位5件）
    if bad_patterns:
        avoid = ", ".join(f"avoid {p}" for p in bad_patterns[:5])
        prompt += f", {avoid}"

    return prompt


def _post_to_hf(api_url: str, payload: dict, hf_token: str) -> bytes:
    """HF Inference API にリクエストを送信してバイナリを返す"""
    headers = {"Authorization": f"Bearer {hf_token}"}
    res = requests.post(api_url, headers=headers, json=payload, timeout=120)
    if res.status_code == 200 and len(res.content) > 10000:
        return res.content
    raise Exception(f"HF API エラー {res.status_code}: {res.text[:300]}")


def generate_image(
    prompt: str,
    seed: int = None,
    output_path: str = None,
    theme: str = "",
    slide_type: str = "",
) -> tuple:
    """
    HF FLUX.1-schnell で背景画像を1枚生成する。
    HF_TOKEN 未設定の場合は Pollinations.ai にフォールバック。

    Returns:
        (保存先パス, 使用したseed)
    """
    if seed is None:
        seed = random.randint(1, 2147483647)

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        output_path = os.path.join(BACKGROUNDS_DIR, f"hf_{timestamp}.jpg")

    hf_token = os.getenv("HF_TOKEN")

    # HF_TOKEN が未設定なら Pollinations.ai にフォールバック
    if not hf_token:
        print("    HF_TOKEN 未設定 → Pollinations.ai にフォールバック")
        return _fallback_pollinations(prompt, seed, output_path)

    full_prompt = _build_full_prompt(prompt)

    # FLUX.1-schnell で試みる（64の倍数でないと失敗するため 1080x1344）
    payload_flux = {
        "inputs": full_prompt,
        "parameters": {
            "seed": seed,
            "width": 1080,
            "height": 1344,
            "num_inference_steps": 4,
            "guidance_scale": 0.0,
        },
    }

    print(f"    HF FLUX.1-schnell で生成中（seed={seed}）...")
    try:
        content = _post_to_hf(HF_API_URL, payload_flux, hf_token)
    except Exception as e:
        print(f"    FLUX.1-schnell 失敗: {e}\n    → SDXL にフォールバック...")
        # SDXL フォールバック
        payload_sdxl = {
            "inputs": full_prompt,
            "parameters": {"seed": seed, "width": 1024, "height": 1024},
        }
        try:
            content = _post_to_hf(FALLBACK_API_URL, payload_sdxl, hf_token)
        except Exception as e2:
            print(f"    SDXL も失敗: {e2}\n    → Pollinations.ai にフォールバック")
            return _fallback_pollinations(prompt, seed, output_path)

    # 1080x1350 にリサイズして保存
    img = Image.open(BytesIO(content)).convert("RGB")
    img = img.resize((1080, 1350), Image.LANCZOS)
    img.save(output_path, "JPEG", quality=92)

    print(f"    → 保存: {output_path}")
    return output_path, seed


def _fallback_pollinations(prompt: str, seed: int, output_path: str) -> tuple:
    """Pollinations.ai にフォールバックして画像を生成"""
    import urllib.parse
    full_prompt = f"{prompt}, soft light, elegant, minimal background, no text, no watermark, photography"
    encoded = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1350&nologo=true&seed={seed}"
    try:
        res = requests.get(url, timeout=120)
        if res.status_code == 200 and len(res.content) > 10000:
            with open(output_path, "wb") as f:
                f.write(res.content)
            return output_path, seed
    except Exception as e:
        raise Exception(f"Pollinations.ai も失敗: {e}")
    raise Exception("Pollinations.ai: 応答が不正")


if __name__ == "__main__":
    # 単体テスト: 1枚生成して保存
    os.makedirs(BACKGROUNDS_DIR, exist_ok=True)
    path, used_seed = generate_image(
        prompt="Japanese esthetic salon, soft pink roses, elegant white marble interior",
        theme="reward",
        slide_type="cover",
    )
    print(f"生成完了: {path} (seed={used_seed})")
