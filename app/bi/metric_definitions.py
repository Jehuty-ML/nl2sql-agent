"""LumenLearn 指标口径（与事件字典一致）。"""

METRIC_DEFINITIONS = {
    "DAU": {
        "formula": "当日 $AppViewScreen/$MPViewScreen 且 identity_login_id 非空，按登录 ID 去重",
        "notes": "登录账号级日活",
    },
    "新增学员": {
        "formula": "当日 event='SignUp' 按 distinct_id 去重",
        "notes": "",
    },
    "完课率": {
        "formula": "CompleteLesson 次数 / StartLesson 次数",
        "notes": "默认次数比",
    },
    "练习转化率": {
        "formula": "SubmitExercise UV / CompleteLesson UV",
        "notes": "",
    },
    "学习漏斗": {
        "formula": "ViewLearningPath → StartLesson → CompleteLesson → SubmitExercise",
        "notes": "默认 UV",
    },
    "次日留存": {
        "formula": "SignUp cohort 在 reg_date+1 有屏浏览",
        "notes": "设备级 distinct_id",
    },
    "七日留存": {
        "formula": "SignUp cohort 在 reg_date+7 有屏浏览",
        "notes": "设备级 distinct_id",
    },
}
