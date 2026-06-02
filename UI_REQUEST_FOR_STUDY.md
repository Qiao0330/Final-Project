# UI Request for Study Mode

這份文件是給負責 Study Mode 的同學和他的 Codex 用的。

我們的 UI 會做成 GTO Wizard 風格的 Study 頁面，但是 UI 不會直接讀你的內部演算法。請你提供一個穩定的「輸出格式」，UI 只負責顯示你給的資料。

## 目標

請提供一個 Study Mode 的資料介面，讓 UI 可以顯示「使用者當下輸入的一手牌分析」。

目前專案不要求一次顯示所有手牌 range。如果你之後有做出頻率或 combos，也可以放進同一個格式裡，UI 會支援。

## 請提供的 function

請建立或修改一個檔案，例如：

```text
study_adapter.py
```

裡面提供這個 function：

```python
def get_study_view_data(request: dict) -> dict:
    ...
```

UI 會呼叫這個 function，傳入使用者輸入的牌局資料，然後拿回一個 dict 顯示在畫面上。

## UI 會傳給你的 request 格式

```python
request = {
    "hero_position": "BB",
    "hero_hand": "8s2s",
    "pot_bb": 44.5,
    "call_amount_bb": 1.5,
    "raise_amount_bb": 100.0,
    "simulations": 10000,
    "action_history": [
        {"position": "UTG", "action": "raise", "amount": 2.5},
        {"position": "HJ", "action": "fold", "amount": 0.0},
        {"position": "CO", "action": "call", "amount": 2.5},
    ],
    "active_opponent_count": 2
}
```

欄位說明：

- `hero_position`: 使用者的位置，可能是 `UTG`, `HJ`, `CO`, `BTN`, `SB`, `BB`
- `hero_hand`: 使用者手牌，例如 `AhKs`, `8s2s`
- `pot_bb`: 目前底池，單位是 BB
- `call_amount_bb`: 如果要跟注，需要補多少 BB
- `raise_amount_bb`: 如果要加注或 all-in，需要投入多少 BB
- `simulations`: Monte Carlo 模擬次數
- `action_history`: 目前牌局前面的行動紀錄
- `active_opponent_count`: 還沒棄牌、可能跟 hero 對抗的對手數

如果你目前不需要某些欄位，可以先忽略，但不要改欄位名稱。

## 請回傳給 UI 的格式

請回傳：

```python
study_data = {
    "mode": "study",
    "hero_position": "BB",
    "hero_hand": "8s2s",
    "pot_bb": 44.5,
    "call_amount_bb": 1.5,
    "pot_odds": 37.3,
    "stacks": {
        "UTG": 100.0,
        "HJ": 97.5,
        "CO": 97.5,
        "BTN": 89.0,
        "SB": 72.5,
        "BB": 99.0
    },
    "actions": [
        {
            "name": "All-in",
            "frequency": 1.5,
            "ev": 0.12,
            "combos": 20.49,
            "is_recommended": False
        },
        {
            "name": "Fold",
            "frequency": 98.5,
            "ev": 0.0,
            "combos": 1305.51,
            "is_recommended": True
        }
    ],
    "hand_cards": [
        {
            "hand": "8s2s",
            "actions": {
                "All-in": 0.0,
                "Fold": 100.0
            },
            "recommended": "Fold",
            "equity": 12.4,
            "ev": 0.0
        }
    ],
    "metrics": {
        "equity": 12.4,
        "win_rate": 10.1,
        "tie_rate": 4.6,
        "loss_rate": 85.3,
        "ev_fold": 0.0,
        "ev_call": -1.2,
        "ev_raise": -3.5
    },
    "explanation": "This hand has low equity against the active opponents, so folding is recommended."
}
```

## 如果你還沒有頻率，請這樣回傳

如果目前只能算出單一建議，例如 `Fold`，還不能算 GTO Wizard 那種頻率，請先回傳：

```python
"actions": [
    {
        "name": "Fold",
        "frequency": 100.0,
        "ev": 0.0,
        "combos": None,
        "is_recommended": True
    },
    {
        "name": "Call",
        "frequency": 0.0,
        "ev": -1.2,
        "combos": None,
        "is_recommended": False
    },
    {
        "name": "Raise",
        "frequency": 0.0,
        "ev": -3.5,
        "combos": None,
        "is_recommended": False
    }
]
```

也就是：

- 推薦動作給 `100.0`
- 其他動作給 `0.0`
- 還沒做 combos 就填 `None`

## 你需要支援的 action 名稱

請盡量使用這些名字：

```text
Fold
Call
Raise
All-in
Check
```

如果你要新增其他名稱，請先跟 UI 這邊說。

## 最重要的要求

請不要讓 UI 需要知道你的內部計算細節。

UI 只會做這件事：

```python
study_data = get_study_view_data(request)
```

然後把 `study_data` 顯示出來。

如果你未來新增真正的頻率、combos、range 計算，只要保持這個輸出格式，UI 就不用大改。
