import httpx


def create_device_client(base_url: str, device_id: str, device_secret: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers={"X-Device-Id": device_id, "X-Device-Secret": device_secret},
        timeout=10,
    )
