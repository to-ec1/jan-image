import os
import io
import time
import random
import urllib.request
import urllib.parse
from PIL import Image

from ddg import Browser

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# -----------------------------
# Google OAuth
# -----------------------------

creds = Credentials(
    token=None,
    refresh_token=REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    scopes=SCOPES
)

print("OAuth開始")
creds.refresh(Request())
print("OAuth完了")

print("Sheets初期化")
sheets = build("sheets", "v4", credentials=creds)
print("Drive初期化")
drive = build("drive", "v3", credentials=creds)
print("初期化完了")

# -----------------------------
# Spreadsheet取得
# -----------------------------

result = sheets.spreadsheets().values().get(
    spreadsheetId=SPREADSHEET_ID,
    range="image!A:F"
).execute()

rows = result.get("values", [])

print(f"取得行数: {len(rows)}")

# -----------------------------
# JAN候補を抽出
# -----------------------------

targets = []

for row_index, row in enumerate(rows[1:], start=2):

    def cell(col):
        index = ord(col) - ord("A")
        return row[index].strip() if len(row) > index else ""

    product = cell("A")
    jan1 = cell("B")
    jan2 = cell("C")
    image1 = cell("D")
    image2 = cell("E")
    image3 = cell("F")

    if image1 or image2 or image3:
        continue

    if jan1:
        jan = jan1
    elif jan2:
        jan = jan2
    else:
        continue

    targets.append((row_index, jan, product))

print(f"処理対象: {len(targets)}件")

# -----------------------------
# 優先順位
# -----------------------------

PRIORITY = {
    "rakuten.co.jp": 1,
    "r10s.jp": 1,
    "yahoo.co.jp": 2,
    "yimg.jp": 2,
    "amazon.co.jp": 3,
    "amazon.jp": 3,
    "yodobashi.com": 4,
}

KNOWN_OTHER = {
    "cainz.com",
    "lohaco.yahoo.co.jp",
    "askul.co.jp",
    "biccamera.com",
    "yamada-denkiweb.com",
    "nojima.co.jp",
    "joshinweb.jp",
}


def get_domain(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def get_priority(img):
    image_url = getattr(img, "image", "")
    page_url = getattr(img, "url", "")
    domains = [get_domain(image_url), get_domain(page_url)]

    for domain in domains:
        for key, priority in PRIORITY.items():
            if key in domain:
                return priority

    for domain in domains:
        for key in KNOWN_OTHER:
            if key in domain:
                return 6

    return 5


# -----------------------------
# 画像ダウンロード
# -----------------------------

def download_image(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131 Safari/537.36"
        }
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()

    if len(data) < 5000:
        raise ValueError("画像サイズが小さすぎます")

    image = Image.open(io.BytesIO(data))
    image.load()

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95)

    return output.getvalue()


# -----------------------------
# Driveアップロード
# -----------------------------

def upload_drive(data, filename):
    metadata = {
        "name": filename,
        "parents": [DRIVE_FOLDER_ID]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(data),
        mimetype="image/jpeg",
        resumable=False
    )

    file = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id"
    ).execute()

    return file["id"]


# -----------------------------
# Sheets更新
# -----------------------------

def update_sheet(row_number, ids):
    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"image!D{row_number}:F{row_number}",
        valueInputOption="RAW",
        body={"values": [ids]}
    ).execute()


# -----------------------------
# メイン処理
# -----------------------------

browser = Browser()

processed = 0
skipped = 0

for row_number, jan, product in targets:

    print("")
    print("=" * 60)
    print(f"行: {row_number}")
    print(f"商品: {product}")
    print(f"JAN: {jan}")
    print("=" * 60)

    try:
        images = browser.images(
            query=jan,
            region="jp-jp",
            safesearch=True,
            limit=50
        )

        if not images:
            print("画像検索結果なし")
            skipped += 1
            continue

        candidates = sorted(
            images,
            key=lambda img: (
                get_priority(img),
                -(
                    (getattr(img, "width", 0) or 0)
                    * (getattr(img, "height", 0) or 0)
                )
            )
        )

        selected_ids = []
        used_urls = set()

        for img in candidates:

            if len(selected_ids) >= 3:
                break

            image_url = getattr(img, "image", "")

            if not image_url or image_url in used_urls:
                continue

            used_urls.add(image_url)

            priority = get_priority(img)

            print(f"\n候補: 優先順位={priority}")
            print(f"タイトル: {img.title}")
            print(f"画像URL: {image_url}")
            print(f"元ページ: {img.url}")
            print(f"サイズ: {img.width}x{img.height}")

            try:
                data = download_image(image_url)
                number = len(selected_ids) + 1
                filename = f"{jan}_{number:02d}.jpg"
                file_id = upload_drive(data, filename)
                selected_ids.append(file_id)
                print(f"Drive保存成功: {filename}")
                print(f"画像ID: {file_id}")

            except Exception as e:
                print(f"画像DL失敗: {e}")
                continue

        if not selected_ids:
            print("画像取得0枚 → スキップ")
            skipped += 1
            continue

        while len(selected_ids) < 3:
            selected_ids.append("")

        update_sheet(row_number, selected_ids[:3])

        print(f"\nSheets更新成功: D{row_number}:F{row_number}")

        processed += 1

        wait_seconds = random.randint(8, 20)
        print(f"次の検索まで {wait_seconds}秒待機")
        time.sleep(wait_seconds)

    except Exception as e:
        print(f"JAN {jan} の処理エラー: {e}")
        time.sleep(random.randint(15, 30))

print("")
print("=" * 60)
print("処理終了")
print(f"成功: {processed}")
print(f"スキップ: {skipped}")
print("=" * 60)
