from modules.today_learning.module import TodayLearningModule


def test_capability_graph_uses_live_mastery_and_keeps_unassessed_points():
    points = [
        {
            "knowledge_point_id": 7,
            "knowledge_point_code": "kp-linear",
            "name": "线性回归",
            "description": "用连续特征预测数值。",
            "mastery_score": 0.82,
            "confidence": 0.9,
        },
        {
            "knowledge_point_id": 8,
            "knowledge_point_code": "kp-cluster",
            "name": "聚类",
            "description": "按相似性分组。",
            "mastery_score": 0.0,
            "confidence": 0.2,
        },
    ]
    tasks = TodayLearningModule._attach_knowledge_points(
        [{"id": "42", "title": "阅读：第一章—线性回归（15分钟）", "reason": "补强", "description": "阅读任务"}],
        points,
    )

    graph = TodayLearningModule._knowledge_graph([], "掌握机器学习", tasks, mastery_points=points)

    assert tasks[0]["knowledgePointIds"] == ["kp-linear"]
    assert graph["nodes"] == [
        {
            "id": "kp-linear",
            "label": "线性回归",
            "status": "good",
            "accuracy": None,
            "masteryScore": 0.82,
            "taskId": "42",
            "reason": "补强",
            "description": "用连续特征预测数值。",
        },
        {
            "id": "kp-cluster",
            "label": "聚类",
            "status": "unassessed",
            "accuracy": None,
            "masteryScore": 0.0,
            "taskId": None,
            "reason": "",
            "description": "按相似性分组。",
        },
    ]
