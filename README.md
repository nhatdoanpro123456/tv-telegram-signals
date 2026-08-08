# Bollinger + Supertrend + EMA200 → Telegram (100% Miễn Phí)

Script Python này tính lại chính xác logic trong indicator Pine Script của bạn
(Bollinger 20/2, Supertrend 10/3, EMA200, điều kiện Buy/Sell + counter-trend),
lấy dữ liệu từ Binance (miễn phí, không cần API key), và tự động gửi tín hiệu
Buy/Sell về Telegram mỗi khi nến 4H đóng — chạy 24/7 miễn phí bằng GitHub Actions.

## Bước 1 — Tạo Telegram Bot (2 phút)

1. Mở Telegram, tìm **@BotFather**, gõ `/newbot`.
2. Đặt tên bot (bất kỳ), đặt username (phải kết thúc bằng `bot`, vd: `my_signal_alert_bot`).
3. BotFather trả về một **Token** dạng `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` → lưu lại.
4. Tạo một nhóm Telegram riêng (hoặc dùng chat cá nhân với bot), **thêm bot vào nhóm**.
5. Lấy **Chat ID**:
   - Gửi thử 1 tin nhắn bất kỳ vào nhóm/chat đó.
   - Mở trình duyệt, vào:
     `https://api.telegram.org/bot<TOKEN>/getUpdates`
     (thay `<TOKEN>` bằng token ở bước 3)
   - Tìm giá trị `"chat":{"id": -1001234567890, ...}` → đó là Chat ID (số âm nếu là group).

## Bước 2 — Tạo GitHub repo (miễn phí)

1. Vào https://github.com → **New repository** → đặt tên (vd: `tv-telegram-signals`) → Create.
2. Upload toàn bộ các file trong thư mục này lên repo (giữ đúng cấu trúc thư mục,
   đặc biệt là `.github/workflows/check_signals.yml`):
   - `signal_checker.py`
   - `requirements.txt`
   - `.github/workflows/check_signals.yml`

   Cách dễ nhất: vào repo → **Add file → Upload files** → kéo thả các file vào
   (tạo đúng đường dẫn `.github/workflows/check_signals.yml`, GitHub sẽ tự tạo thư mục).

## Bước 3 — Khai báo Secrets & Variables (để giấu Token, không lộ public)

Vào repo → **Settings → Secrets and variables → Actions**:

**Tab "Secrets" → New repository secret:**
| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token bot lấy ở Bước 1 |
| `TELEGRAM_CHAT_ID` | chat id lấy ở Bước 1 |

**Tab "Variables" → New repository variable:**
| Name | Value |
|---|---|
| `SYMBOLS` | `BTCUSDT,ETHUSDT` (danh sách coin, cách nhau bởi dấu phẩy, không dấu cách) |
| `INTERVAL` | `4h` |

## Bước 4 — Kích hoạt & Test

1. Vào tab **Actions** của repo → nếu thấy thông báo "Workflows aren't running", bấm
   **I understand my workflows, go ahead and enable them**.
2. Chọn workflow **"Check Buy/Sell Signals"** ở cột trái → **Run workflow** (nút màu xanh
   bên phải) → **Run workflow** để test thủ công ngay, không cần chờ lịch.
3. Đợi ~30 giây, bấm vào lần chạy vừa xong để xem log — sẽ thấy dòng như
   `[BTCUSDT] Khong co tin hieu moi o nen gan nhat` (bình thường, vì không phải lúc nào
   cũng có tín hiệu) hoặc `BUY signal sent.` nếu đúng lúc có tín hiệu.
4. Nếu có lỗi (vd sai Token) → log sẽ báo rõ, sửa lại Secret rồi Run workflow lại.

Từ giờ, GitHub Actions sẽ **tự động chạy mỗi khi nến 4H đóng** (không cần bạn làm gì thêm),
kiểm tra tất cả symbol trong `SYMBOLS`, và gửi Telegram nếu có tín hiệu Buy/Sell/Buy*/Sell*.

## Lưu ý quan trọng

- **Hoàn toàn miễn phí**: GitHub Actions cho phép 2.000 phút chạy/tháng miễn phí với repo
  public (script này chạy ~30s mỗi lần, 6 lần/ngày → tốn ~90 phút/tháng, dư sức).
- Nếu repo **private**, gói free vẫn có 2.000 phút/tháng cho tài khoản cá nhân — vẫn đủ dùng.
- Muốn thêm/bớt coin: chỉ cần sửa biến `SYMBOLS` trong Settings → Variables, không cần sửa code.
- Muốn đổi khung thời gian: sửa `INTERVAL` (giá trị hợp lệ theo Binance: `1m,5m,15m,1h,4h,1d,...`)
  — nhớ đổi luôn lịch cron trong `check_signals.yml` cho khớp khung giờ đóng nến.
- Logic đã được viết lại sát nhất có thể với Pine Script gốc (Supertrend dùng Wilder RMA cho ATR,
  đúng cách TradingView tính `ta.atr`), nhưng vì Binance và TradingView có thể lấy dữ liệu nến
  hơi khác nhau (nguồn giá, độ trễ), tín hiệu có thể lệch nhẹ so với trên chart TradingView.
  Nên đối chiếu vài lần đầu trước khi tin tưởng hoàn toàn.
