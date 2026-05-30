"""Sync BPR deviation analysis results to a SharePoint list via Microsoft Graph API.

Usage:
    uv run python -m novartis_agentic_demo.sync_to_sharepoint

Authentication: device code flow (interactive browser login, no app registration needed).
"""

import json
from pathlib import Path

import msal
import requests

# ── SharePoint config ────────────────────────────────────────────────────────
SITE_HOSTNAME = "liuonline.sharepoint.com"
SITE_PATH = "/sites/PharmaQA"
LIST_NAME = "DeviationRecords"

# ── Auth config (Microsoft Graph Command Line Tools — public client, no secret needed) ──
CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
TENANT_ID = "common"
SCOPES = ["https://graph.microsoft.com/Sites.ReadWrite.All"]

OUTPUT_DIR = Path(__file__).parent.parent.parent / "outputs"
GRAPH = "https://graph.microsoft.com/v1.0"


def get_token() -> str:
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )
    flow = app.initiate_device_flow(scopes=SCOPES)
    print("\n" + flow["message"] + "\n")   # prints the "go to microsoft.com/devicelogin" instruction
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")
    return result["access_token"]


def _get(token: str, url: str) -> dict:
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json()


def get_site_id(token: str) -> str:
    data = _get(token, f"{GRAPH}/sites/{SITE_HOSTNAME}:{SITE_PATH}")
    return data["id"]


def get_list_id(token: str, site_id: str) -> str:
    data = _get(token, f"{GRAPH}/sites/{site_id}/lists/{LIST_NAME}")
    return data["id"]


def create_item(token: str, site_id: str, list_id: str, fields: dict) -> str:
    resp = requests.post(
        f"{GRAPH}/sites/{site_id}/lists/{list_id}/items",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def load_items() -> list[dict]:
    """Read sharepoint_item from each BATCH-*.json in outputs/."""
    items = []
    for path in sorted(OUTPUT_DIR.glob("BATCH-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        sp = data.get("sharepoint_item", {})
        sp["_source_file"] = path.name   # keep for logging, stripped before upload
        items.append(sp)
    return items


def main():
    items = load_items()
    if not items:
        print(f"No BATCH-*.json files found in {OUTPUT_DIR}/. Run the analysis first.")
        return

    print(f"Found {len(items)} batch result(s) to sync to '{LIST_NAME}'.")
    token = get_token()

    site_id = get_site_id(token)
    list_id = get_list_id(token, site_id)
    print(f"Connected → site: {SITE_PATH}  list: {LIST_NAME}")

    success, failed = 0, []
    for item in items:
        source = item.pop("_source_file")
        try:
            item_id = create_item(token, site_id, list_id, item)
            print(f"  ✓  {item['BatchID']:12s}  (SharePoint item id: {item_id})")
            success += 1
        except requests.HTTPError as e:
            print(f"  ✗  {item['BatchID']:12s}  ERROR: {e.response.text}")
            failed.append(source)

    print(f"\n{'─'*50}")
    print(f"Synced: {success}/{len(items)}  |  Failed: {len(failed)}")
    if failed:
        print(f"Failed files: {', '.join(failed)}")


if __name__ == "__main__":
    main()
