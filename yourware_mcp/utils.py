def urljoin(base: str, url: str) -> str:
    return "/".join([base.rstrip("/"), url.lstrip("/")])
