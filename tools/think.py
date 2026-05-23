"""思考工具：驱动 ReAct 多轮深度推理"""

import json

from tools.registry import registry


def handle_think(args: dict) -> str:
    """保存中间思考过程，驱动 ReAct 循环继续

    Args:
        args: {"thought": str}

    Returns:
        固定确认字符串
    """
    return json.dumps({"status": "ok", "message": "思考结果已保存"}, ensure_ascii=False)


registry.register(
    name="think",
    schema={
        "type": "function",
        "function": {
            "name": "think",
            "description": (
                "保存当前轮的中间思考结果，驱动多轮深度推理。"
                "当你发现没有合适的工具可以调用，但还需要进一步分析、"
                "分解问题或推演后续步骤时，使用此工具将当前思考记录下来，"
                "以便在下一轮继续推进任务。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "当前轮的中间思考内容，包括分析进展、待解决问题、后续计划等",
                    },
                },
                "required": ["thought"],
            },
        },
    },
    handler=handle_think,
    parallel_safe=True,
)