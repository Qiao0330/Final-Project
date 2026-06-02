# UI Request for Trainer Mode

這份文件是給負責 Trainer Mode 的同學和他的 Codex 用的。

我們的 UI 會做成 GTO Wizard 風格的 Trainer 頁面。Trainer Mode 可以先做簡化版：系統出一題，使用者選 Fold / Call / Raise，程式判斷答案並給分。

UI 不會直接讀你的內部演算法。請你提供固定 function 和固定資料格式。

## 目標

請提供一個 Trainer Mode 的資料介面，讓 UI 可以完成這個流程：

1. UI 向 trainer 要一題題目
2. UI 顯示位置、手牌、行動歷史、底池
3. 使用者按 Fold / Call / Raise
4. UI 把使用者答案送回 trainer
5. trainer 回傳正確答案、分數、說明

## 請提供的檔案

請建立或修改一個檔案，例如：

```text
trainer_adapter.py
```

裡面提供兩個 function：

```python
def get_trainer_question(settings: dict | None = None) -> dict:
    ...


def grade_trainer_answer(question_id: str, user_action: str) -> dict:
    ...
```

## Function 1: get_trainer_question

UI 會呼叫：

```python
question = get_trainer_question(settings)
```

`settings` 可以先不用做很複雜。初版可以支援：

```python
settings = {
    "difficulty": "normal",
    "mode": "preflop",
    "simulations": 10000
}
```

如果你目前不需要 settings，可以忽略，但不要讓 function 壞掉。

## 請回傳的 question 格式

```python
question = {
    "question_id": "q_0001",
    "mode": "trainer",
    "street": "preflop",
    "hero_position": "BTN",
    "hero_hand": "AhKh",
    "pot_bb": 3.5,
    "call_amount_bb": 1.0,
    "raise_amount_bb": 2.5,
    "action_history": [
        {"position": "UTG", "action": "fold", "amount": 0.0},
        {"position": "HJ", "action": "fold", "amount": 0.0},
        {"position": "CO", "action": "fold", "amount": 0.0}
    ],
    "available_actions": ["Fold", "Call", "Raise"],
    "stacks": {
        "UTG": 100.0,
        "HJ": 100.0,
        "CO": 100.0,
        "BTN": 100.0,
        "SB": 99.5,
        "BB": 99.0
    }
}
```

欄位說明：

- `question_id`: 每題唯一 ID，之後評分會用到
- `street`: 初版可以固定 `preflop`
- `hero_position`: hero 的位置
- `hero_hand`: hero 手牌
- `pot_bb`: 目前底池
- `call_amount_bb`: 跟注需要多少
- `raise_amount_bb`: 加注需要多少
- `action_history`: 這題前面發生過的行動
- `available_actions`: 使用者可以選的按鈕
- `stacks`: 每個位置剩餘籌碼，可先用預設值

## Function 2: grade_trainer_answer

使用者按答案後，UI 會呼叫：

```python
result = grade_trainer_answer(question_id, user_action)
```

例如：

```python
result = grade_trainer_answer("q_0001", "Call")
```

請回傳：

```python
result = {
    "question_id": "q_0001",
    "user_action": "Call",
    "correct_action": "Raise",
    "is_correct": False,
    "score": 65,
    "actions": [
        {
            "name": "Fold",
            "frequency": 0.0,
            "ev": 0.0,
            "is_best": False
        },
        {
            "name": "Call",
            "frequency": 15.0,
            "ev": 1.1,
            "is_best": False
        },
        {
            "name": "Raise",
            "frequency": 85.0,
            "ev": 2.4,
            "is_best": True
        }
    ],
    "feedback": "AQs/AKs type hands are strong on the button after folds, so raising is usually better than calling.",
    "metrics": {
        "equity": 63.2,
        "ev_fold": 0.0,
        "ev_call": 1.1,
        "ev_raise": 2.4
    }
}
```

## 如果你還沒有頻率，請這樣回傳

如果你目前只知道正確答案，還沒有完整頻率，請先回傳：

```python
"actions": [
    {
        "name": "Fold",
        "frequency": 0.0,
        "ev": 0.0,
        "is_best": False
    },
    {
        "name": "Call",
        "frequency": 0.0,
        "ev": 1.1,
        "is_best": False
    },
    {
        "name": "Raise",
        "frequency": 100.0,
        "ev": 2.4,
        "is_best": True
    }
]
```

也就是：

- 正確答案給 `100.0`
- 其他答案給 `0.0`
- EV 如果還沒有，可以填 `None`

## 你需要支援的 action 名稱

請盡量使用這些名字：

```text
Fold
Call
Raise
All-in
Check
```

如果你要新增其他 action，請先跟 UI 這邊說。

## 初版 Trainer 可以很簡單

初版不需要完整做到 GTO Wizard 的所有功能。

可以先做到：

- 隨機產生 preflop 題目
- 題目包含 hero 位置、手牌、前面行動
- 使用者選 Fold / Call / Raise
- 系統回傳正確答案
- 系統給 `0-100` 分
- 系統給一段簡短解釋

## 最重要的要求

請讓 UI 只需要做這兩件事：

```python
question = get_trainer_question(settings)
result = grade_trainer_answer(question["question_id"], user_action)
```

UI 不應該需要知道 trainer 內部怎麼產生題目、怎麼計分、怎麼判斷正確答案。

只要你保持這兩個 function 和資料格式，UI 就可以先完成，之後你再升級 trainer 的演算法也不會影響 UI。
