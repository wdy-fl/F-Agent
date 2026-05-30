"""Web 搜索与网页抓取工具"""

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from config.settings import get_config
from tools.registry import registry


BAIDU_AI_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


def web_search(args: dict) -> str:
    """执行 Web 搜索（使用百度千帆 AI Search API）

    Args:
        args: {"query": str, "max_results": int}

    Returns:
        搜索结果列表
    """
    query = args.get("query", "")
    max_results = args.get("max_results", 5)

    if not query:
        return json.dumps({"error": "No query provided"}, ensure_ascii=False)

    try:
        config = get_config()
        api_key = config.tools.baidu_ai_search_api_key
        if not api_key:
            return json.dumps(
                {"error": "Search failed: missing tools.baidu_ai_search_api_key"},
                ensure_ascii=False,
            )

        payload = {
            "messages": [{"content": query, "role": "user"}],
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": max_results}],
            "edition": "standard",
        }
        req = Request(
            BAIDU_AI_SEARCH_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "X-Appbuilder-Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(req, timeout=config.tools.baidu_ai_search_timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        error_code = result.get("code")
        if error_code not in (None, "", 0):
            message = result.get("message", "unknown error")
            return json.dumps(
                {"error": f"Search failed: API error {error_code}: {message}"},
                ensure_ascii=False,
            )

        references = result.get("references", [])
        results = []
        for ref in references[:max_results]:
            title = ref.get("title", "")
            link = ref.get("url", "")
            if title and link:
                item = {"title": title, "url": link}
                content = ref.get("content", "")
                if content:
                    item["snippet"] = content
                results.append(item)

        return json.dumps({
            "query": query,
            "results": results,
            "count": len(results),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {e}"}, ensure_ascii=False)


def web_fetch(args: dict) -> str:
    """抓取网页内容

    Args:
        args: {"url": str, "max_length": int}

    Returns:
        网页文本内容
    """
    url = args.get("url", "")
    max_length = args.get("max_length", 10000)

    if not url:
        return json.dumps({"error": "No URL provided"}, ensure_ascii=False)

    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()

        # 尝试 UTF-8 解码
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

        # 简单去除 HTML 标签（纯文本提取）
        if "html" in content_type.lower():
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_length:
            text = text[:max_length] + "\n...[truncated]"

        return json.dumps({
            "url": url,
            "content": text,
            "length": len(text),
        }, ensure_ascii=False)
    except URLError as e:
        return json.dumps({"error": f"Fetch failed: {e}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 自注册
registry.register(
    name="web_search",
    schema={
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "使用搜索引擎搜索信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "最大结果数，默认 5", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    handler=web_search,
)

registry.register(
    name="web_fetch",
    schema={
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "抓取指定 URL 的网页内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的网页 URL"},
                    "max_length": {"type": "integer", "description": "最大内容长度，默认 10000", "default": 10000},
                },
                "required": ["url"],
            },
        },
    },
    handler=web_fetch,
)
