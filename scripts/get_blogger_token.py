"""Blogger API용 refresh token 1회 발급 스크립트.

사용법:
  1. Google Cloud에서 데스크톱 OAuth 클라이언트 JSON을 받아
     프로젝트 루트에 client_secret.json 으로 저장
  2. pip install google-auth-oauthlib
  3. python scripts/get_blogger_token.py
  4. 출력된 값을 GitHub Secrets에 등록

client_secret.json / token 파일은 커밋하지 말 것.
"""

from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/blogger"]
ROOT = Path(__file__).resolve().parents[1]
CLIENT_SECRET = ROOT / "client_secret.json"


def main():
    if not CLIENT_SECRET.exists():
        print(f"[ERROR] {CLIENT_SECRET} 파일이 없습니다.")
        print("Google Cloud Console에서 데스크톱 OAuth 클라이언트 JSON을 다운로드해")
        print("프로젝트 루트에 client_secret.json 으로 저장하세요.")
        print("자세한 절차: .github/editorial/BLOGGER_API_SETUP.md")
        raise SystemExit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)

    print()
    print("=" * 60)
    print("아래 값을 GitHub Secrets에 등록하세요")
    print("=" * 60)
    print(f"BLOGGER_CLIENT_ID={creds.client_id}")
    print(f"BLOGGER_CLIENT_SECRET={creds.client_secret}")
    print(f"BLOGGER_REFRESH_TOKEN={creds.refresh_token}")
    print()
    print("추가로 BLOGGER_BLOG_ID (Blogger 설정에 있는 숫자 ID)도 등록하세요.")
    print("가이드: .github/editorial/BLOGGER_API_SETUP.md")


if __name__ == "__main__":
    main()
