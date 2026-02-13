import random
import math
from js import setTimeout, document, performance
from pyodide.ffi import create_proxy

# 定数の宣言
INTERVAL = 50               # ボールの移動間隔（ミリ秒）
PLAYER_W = 100              # プレイヤーのバーの幅
PLAYER_Y = 470              # プレイヤーのバーのY座標
PLAYER_MOVE = 30            # プレイヤーのバーの移動量
BALL_SPEED = 15             # ボールの速度
BALL_SIZE = 16              # ボールのサイズ
BLOCK_W = 50                # ブロックの幅
BLOCK_H = 20                # ブロックの高さ
COLS = 400 // BLOCK_W       # ブロックの列数
ROWS = 8                    # ブロックの行数
BLOCK_COLORS = [            #ブロックの色
    "#FFFFFF", "#286399", "#2C6FAB", "#3077B8",
    "#3483C9", "#378BD6", "#3B95E6", "#3F9DF2", "#42A6FF"]

# パドル
PADDLE_IMPULSE = 0.10       # パドル速度(px/tick) → dx へ足す係数（大きいほど左右に飛ぶ）
ACCEL_PER_PX = 0.05         # |パドル速度| 1px/tick あたりの速度倍率の増分
ACCEL_MAX = 0.50          # 1回のヒットでの最大加速
MIN_SPEED = 6               # ボール最低速度
MAX_SPEED = 40              # ボール最高速度（上限）

# グローバル変数の宣言
info = document.getElementById("info") # 情報表示用の要素を取得
canvas = document.getElementById("canvas") # Canvas要素を取得
context = canvas.getContext("2d") # 2D描画コンテキストを取得
start_button = document.getElementById("start_button")

blocks = [] # ブロックのリスト
# ゲームの状態を管理する辞書
game = {
    "score": 0,
    "px": 0,
    "ball_x": 0,
    "ball_y": 0,
    "dx": 0,
    "dy": 0,
    "game_over": True,
    # パドル -------
    "pvx": 0.0,
    "last_px": 0.0,
    "last_t" : 0.0,
}
mouse_active = False  # Canvas内にマウスがある間だけ True

mouse_enter_proxy = None
mouse_leave_proxy = None
mouse_move_proxy  = None
key_down_proxy    = None
loop_proxy        = None

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def init_game():
    """ゲームの初期化"""
    global blocks, game
    # ブロックの初期化
    blocks = [[(y+1)] * COLS for y in range(ROWS)] 
    # スピード
    speed = 10  # 初期値
    # ランダムな角度を作る
    while True:
        angle = random.uniform(200, 340)
        if abs(math.cos(math.radians(angle))) > 0.3:
            break
    rad = math.radians(angle) 
    
    dx = speed * math.cos(rad)
    dy = speed * math.sin(rad)

    px = (canvas.width - PLAYER_W) // 2 # プレイヤーのバーのX座標
    now = performance.now()

    game.update({
        "score":0, # スコア
        "px": px, # プレイヤーのバーのX座標
        "ball_x": canvas.width / 2, # ボールのX座標
        "ball_y": canvas.height / 2, # ボールのY座標
        "dx": dx, 
        "dy": dy,
        "game_over": False, # ゲームオーバー状態
        # パドル------
        "pvx": 0.0,
        "last_px": float(px),
        "last_t": float(now)
    })
    info.innerText = "ブロック崩し"
    
def game_loop():

    """ゲームのメインループ"""
    update_ball() # ボールの位置更新
    draw_screen() # 画面の更新
    # ゲームオーバーでなければ次のループをセット
    if not game["game_over"]:
        setTimeout(loop_proxy, INTERVAL)


def update_ball():
    global dx,dy
    """ボール位置の更新"""
    r = BALL_SIZE / 2

    bx = game["ball_x"] + game["dx"]
    by = game["ball_y"] + game["dy"]

    dx = game["dx"]
    dy = game["dy"]

    # 上壁
    if by - r <= 0:
        by = r
        dy = -dy
    # 左右壁
    if bx - r <= 0:
        bx = r
        dx = -dx
    elif bx + r >= canvas.width:
        bx = canvas.width - r
        dx = -dx
    # プレイヤーバー
    px = game["px"]
    if (by + r >= PLAYER_Y) and (px <= bx <= px + PLAYER_W):
        by = PLAYER_Y - r
        dy = -abs(dy)   # 必ず上に返す
        # 当たった位置で横方向を調整
        hit = (bx - (px + PLAYER_W/2)) / (PLAYER_W/2)
        # パドル -----
        pvx = game.get("pvx", 0.0)  # px / tick
        dx += hit * 1.5 + pvx * PADDLE_IMPULSE

        base = math.hypot(dx,dy)
        if base < 1e-6:
            base = 1e-6
        accel = 1.0 + min(abs(pvx)*ACCEL_PER_PX,ACCEL_MAX)
        new_speed = clamp(base * accel, MIN_SPEED,MAX_SPEED)
        # 方向は保って速度だけ合わせる（正規化）
        k = new_speed / base
        dx *= k
        dy *= k

     # ブロック
    elif check_blocks(bx, by):
        dy = -dy
        game["score"] += 1
        # 加速
        dx *= 1.02
        dy *= 1.02
        # 上限を超えないように
        sp = math.hypot(dx,dy)
        if sp > MAX_SPEED:
            k = MAX_SPEED / sp
            dx *= k
            dy *= k
        
        if game["score"] >= COLS * ROWS:
            game_over("クリア！")
    # 落下
    elif by - r > canvas.height:
        game_over("ゲームオーバー")

    # 状態更新
    game["ball_x"] = bx
    game["ball_y"] = by
    game["dx"] = dx
    game["dy"] = dy

def check_blocks(bx,by):
    """ブロックとの衝突判定"""
    block_x, block_y = int(bx // BLOCK_W), int(by // BLOCK_H)
    if 0 <= block_x < COLS and 0 <= block_y < ROWS:
        if blocks[block_y][block_x] != 0: # ブロックが存在する場合
            blocks[block_y][block_x] = 0 # ブロックを消す
            return True
    return False

def game_over(msg):
    # ゲームオーバー処理
    # スタートボタンの有効化
    document.getElementById("start_button").disabled=False
    # ゲームオーバーとスコアの表示
    info.innerText=f"{msg} スコア: {game['score']}"
    game["game_over"] = True


# ----------  スクリーン描画　-------------
def draw_screen():
    """画面の更新"""
    context.clearRect(0, 0, canvas.width, canvas.height)  # 画面クリア
    # ブロックの描画
    for y in range(ROWS):
        for x in range(COLS):
            if blocks[y][x] == 0:
                continue  # ブロックがなければスキップ
            # ブロックの色を設定して描画
            context.fillStyle = BLOCK_COLORS[blocks[y][x]]
            context.fillRect(x * BLOCK_W, y * BLOCK_H, BLOCK_W - 2, BLOCK_H - 2)
    # プレイヤーのバーの描画
    context.fillStyle = "#011254" # プレイヤーのバーの色
    context.fillRect(game["px"], PLAYER_Y, PLAYER_W, 10) # バーを描画
    # ボールの描画
    context.fillStyle = "#BD1433" # ボールの色
    context.beginPath() # 新しいパスを開始
    context.arc(game["ball_x"], game["ball_y"], BALL_SIZE // 2, 0, 2 * math.pi) # 円を描く
    context.fill() # 円を塗りつぶす

    # スコア表示
    if not game["game_over"]:
        speed = math.hypot(game["dx"], game["dy"])
        info.innerText = (
            f"スコア:{game['score']}  "
            f"pvx:{game['pvx']:.1f}  "
            f"speed:{speed:.1f}"
        )


# -----------  コントロール　-------------
def update_paddle(new_px):
    # パドル一の計算、速度更新
    if game["game_over"]:
        return
    now = float(performance.now())
    last_t = float(game.get("last_t", now))
    last_px = float(game.get("last_px", new_px))

    dt = now - last_t
    if dt < 1.0:
        dt = 1.0 # 0による除算を避ける
    # px/ms → px/tick（INTERVAL分）
    pvx = (float(new_px) - last_px) / dt * INTERVAL

    game["pvx"] = pvx
    game["last_px"] = float(new_px)
    game["last_t"] = now
    game["px"] = new_px
 

def start_button_on_click(event):
    """スタートボタンがクリックされたときの処理"""
    global loop_proxy
    # スタートボタンの無効化
    document.getElementById("start_button").disabled = True
    init_game() # ゲーム初期化
    if loop_proxy is None:
        loop_proxy = create_proxy(game_loop)
    game_loop() # ゲームループ開始

def set_player_x_from_mouse(client_x):
    """マウスのX座標(clientX)からバー位置(px)を計算して反映（水平のみ）"""
    if game["game_over"]:
        return

    rect = canvas.getBoundingClientRect()
    x = client_x - rect.left  # Canvas内のX座標に変換

    # バー中心がマウス位置に来るようにする
    px = x - (PLAYER_W / 2)

    # 画面外に出ないようにクランプ
    if px < 0:
        px = 0
    max_px = canvas.width - PLAYER_W
    if px > max_px:
        px = max_px

    game["px"] = px
    update_paddle(px)
    draw_screen()

def on_mouse_enter(event):
    global mouse_active
    mouse_active = True

def on_mouse_leave(event):
    global mouse_active
    mouse_active = False

def on_mouse_move(event):
    # 「ある領域（=canvas）」に入っている間だけ動かす
    if not mouse_active:
        return
    set_player_x_from_mouse(event.clientX)

def player_move(dx):
    """プレイヤーのバーを移動する"""
    if game["game_over"]:
        return  # ゲームオーバー時は移動しない
    px = game["px"] + dx  # 新しいバーの位置
    if px < 0:
        px = 0
    max_px = canvas.width - PLAYER_W
    if px > max_px:
        px = max_px
    update_paddle(px)
    draw_screen()


def key_down(event):
    """キーが押されたときの処理"""
    if event.key == "ArrowRight":
       player_move(PLAYER_MOVE)  # 右に移動
    elif event.key == "ArrowLeft":
        player_move(-1 * PLAYER_MOVE)  # 左に移動

# リスナー登録（★create_proxyで包んで保持）
def setup_listeners():
    global start_click_proxy, mouse_enter_proxy, mouse_leave_proxy, mouse_move_proxy, key_down_proxy

    start_click_proxy = create_proxy(start_button_on_click)
    mouse_enter_proxy = create_proxy(on_mouse_enter)
    mouse_leave_proxy = create_proxy(on_mouse_leave)
    mouse_move_proxy = create_proxy(on_mouse_move)
    key_down_proxy = create_proxy(key_down)

    start_button.addEventListener("click", start_click_proxy)
    canvas.addEventListener("mouseenter", mouse_enter_proxy)
    canvas.addEventListener("mouseleave", mouse_leave_proxy)
    canvas.addEventListener("mousemove", mouse_move_proxy)
    document.addEventListener("keydown", key_down_proxy)

# 起動時に1回
setup_listeners()
# 準備完了したらボタンを有効化
start_button.disabled = False
start_button.innerText = "ゲームスタート"
info.innerText = "準備完了：スタートを押してください"