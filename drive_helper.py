GITHUB_OWNER = "spikesukeshun"
GITHUB_REPO = "miki-instagram"
GITHUB_BRANCH = "main"


def get_file_url(filename: str) -> str:
    """ファイル名からGitHub rawコンテンツのURLを返す"""
    return f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/{GITHUB_BRANCH}/generated/{filename}"
