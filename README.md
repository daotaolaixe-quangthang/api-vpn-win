# Multi VPN API for Windows

Backend API server Python dùng FastAPI để điều khiển nhiều VPN provider trên Windows qua CLI hoặc native interface của từng app.

Provider hiện có:

- `pia` - Private Internet Access VPN
- `hma` - HMA VPN
- `expressvpn` - ExpressVPN

API chính dùng format chung:

```text
/vpn/{provider}/...
```

Ví dụ:

```text
/vpn/pia/status
/vpn/hma/status
/vpn/expressvpn/status
```

Ngoài ra project vẫn giữ endpoint legacy riêng cho PIA:

```text
/pia/...
```

## 1. Yêu cầu hệ thống

- Windows
- Python 3.10 trở lên
- VPN app đã được cài và đã đăng nhập tài khoản
- Chạy API trên máy có cài VPN app

Đường dẫn mặc định:

```text
PIA CLI: C:\Program Files\Private Internet Access\piactl.exe
PIA GUI: C:\Program Files\Private Internet Access\pia-client.exe

HMA native messaging: C:\Program Files\Privax\HMA VPN\VpnNM.exe
HMA GUI: C:\Program Files\Privax\HMA VPN\Vpn.exe
HMA service: HmaProVpn

ExpressVPN CLI: C:\Program Files\ExpressVPN\expressvpnctl.exe
ExpressVPN GUI: C:\Program Files\ExpressVPN\expressvpn-client.exe
```

## 2. Cài đặt

Mở terminal tại thư mục project:

```bash
cd e:/2WEBApp/api-vpn-win
```

Tạo virtual environment nếu cần:

```bash
python -m venv .venv
.venv/Scripts/activate
```

Cài dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy file cấu hình mẫu:

```bash
cp .env.example .env
```

Chạy server:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mở Swagger UI:

```text
http://127.0.0.1:8000/docs
```

Mở OpenAPI JSON:

```text
http://127.0.0.1:8000/openapi.json
```

## 3. Cấu hình `.env`

File `.env.example` có đầy đủ biến cấu hình:

```env
PIA_CTL_PATH=C:\Program Files\Private Internet Access\piactl.exe
PIA_GUI_PATH=C:\Program Files\Private Internet Access\pia-client.exe
PIA_COMMAND_TIMEOUT_SECONDS=30
PIA_CONNECT_TIMEOUT_SECONDS=90
PIA_RECONNECT_DELAY_SECONDS=3
PIA_REFRESH_MAX_ATTEMPTS=0
PIA_REFRESH_TIMEOUT_SECONDS=180
DEFAULT_VPN_PROVIDER=pia

HMA_NM_PATH=C:\Program Files\Privax\HMA VPN\VpnNM.exe
HMA_GUI_PATH=C:\Program Files\Privax\HMA VPN\Vpn.exe
HMA_SERVICE_NAME=HmaProVpn
HMA_COMMAND_TIMEOUT_SECONDS=30
HMA_CONNECT_TIMEOUT_SECONDS=90
HMA_RECONNECT_DELAY_SECONDS=3
HMA_REFRESH_MAX_ATTEMPTS=1
HMA_REFRESH_TIMEOUT_SECONDS=180

EXPRESSVPN_CTL_PATH=C:\Program Files\ExpressVPN\expressvpnctl.exe
EXPRESSVPN_GUI_PATH=C:\Program Files\ExpressVPN\expressvpn-client.exe
EXPRESSVPN_COMMAND_TIMEOUT_SECONDS=30
EXPRESSVPN_CONNECT_TIMEOUT_SECONDS=90
EXPRESSVPN_RECONNECT_DELAY_SECONDS=3
EXPRESSVPN_REFRESH_MAX_ATTEMPTS=0
EXPRESSVPN_REFRESH_TIMEOUT_SECONDS=180

API_HOST=127.0.0.1
API_PORT=8000
API_KEY=
```

Giải thích biến quan trọng:

| Biến | Ý nghĩa |
| --- | --- |
| `DEFAULT_VPN_PROVIDER` | Provider mặc định khi code gọi provider rỗng. Hiện route public vẫn truyền provider qua URL. |
| `API_KEY` | Nếu rỗng thì không cần auth. Nếu có giá trị thì mọi endpoint VPN cần header `X-API-Key`. |
| `*_COMMAND_TIMEOUT_SECONDS` | Timeout cho một lệnh CLI hoặc native command. |
| `*_CONNECT_TIMEOUT_SECONDS` | Timeout khi chờ trạng thái `Connected` hoặc `Disconnected`. |
| `*_RECONNECT_DELAY_SECONDS` | Thời gian chờ giữa disconnect và connect khi refresh IP. |
| `*_REFRESH_TIMEOUT_SECONDS` | Tổng thời gian tối đa cho `refresh-ip`. Mặc định 180 giây. |
| `*_REFRESH_MAX_ATTEMPTS` | Số lần retry tối đa. Riêng giá trị `0` nghĩa là retry tới khi đổi IP hoặc hết timeout. |

## 4. Auth bằng API key

Nếu `.env` có:

```env
API_KEY=my-secret-key
```

Thì mọi endpoint điều khiển VPN cần header:

```bash
-H "X-API-Key: my-secret-key"
```

Ví dụ:

```bash
curl -H "X-API-Key: my-secret-key" http://127.0.0.1:8000/vpn/pia/status
```

Nếu `API_KEY=` rỗng thì không cần header.

## 5. Format response chung

Mọi response thành công dùng schema:

```json
{
  "ok": true,
  "data": {},
  "warnings": []
}
```

Ví dụ:

```json
{
  "ok": true,
  "data": {
    "provider": "pia",
    "connectionstate": "Connected",
    "region": "vietnam",
    "pubip": "118.71.64.61",
    "vpnip": "173.239.247.145"
  },
  "warnings": []
}
```

Khi endpoint `refresh-ip` không đổi được IP, API trả lỗi HTTP, không trả `ok:true`.

Format lỗi thường gặp:

```json
{
  "detail": {
    "error": "PIA command failed",
    "command": ["C:\\Program Files\\Private Internet Access\\piactl.exe", "connect"],
    "stderr": "...",
    "returncode": 1
  }
}
```

## 6. Mã lỗi HTTP thường gặp

| Status | Ý nghĩa |
| --- | --- |
| 400 | Region sai format hoặc input không hợp lệ. |
| 401 | Sai hoặc thiếu `X-API-Key`. |
| 404 | Provider không hỗ trợ. |
| 409 | Không có VPN IP hợp lệ trước khi refresh, hoặc provider yêu cầu đang connected. |
| 502 | CLI hoặc native command trả lỗi. |
| 503 | Không tìm thấy file executable của provider. |
| 504 | Timeout khi chạy command, connect, disconnect, hoặc refresh IP. |

## 7. Provider được hỗ trợ

| Provider | URL name | Ghi chú |
| --- | --- | --- |
| Private Internet Access | `pia` | Dùng `piactl.exe`. Có endpoint legacy `/pia/*`. |
| HMA VPN | `hma` | Dùng `VpnNM.exe` native messaging. |
| ExpressVPN | `expressvpn` | Dùng `expressvpnctl.exe`. Cần GUI đang chạy hoặc bật background mode. |

## 8. API chung cho mọi provider

Các endpoint dưới đây dùng `{provider}` là một trong:

```text
pia
hma
expressvpn
```

### 8.1 Health check

```text
GET /health
```

Không cần API key.

Ví dụ:

```bash
curl http://127.0.0.1:8000/health
```

Response:

```json
{
  "ok": true,
  "data": {
    "service": "multi-vpn-api"
  },
  "warnings": []
}
```

### 8.2 Launch GUI

```text
POST /vpn/{provider}/launch
```

Mở app GUI của provider.

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8000/vpn/pia/launch
curl -X POST http://127.0.0.1:8000/vpn/hma/launch
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/launch
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "expressvpn",
    "message": "ExpressVPN GUI launched"
  },
  "warnings": []
}
```

### 8.3 Enable background mode

```text
POST /vpn/{provider}/background/enable
```

Bật hoặc mô tả background mode của provider.

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8000/vpn/pia/background/enable
curl -X POST http://127.0.0.1:8000/vpn/hma/background/enable
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/background/enable
```

Ghi chú theo provider:

- PIA chạy `piactl background enable`.
- ExpressVPN chạy `expressvpnctl background enable`.
- HMA dùng Windows service, endpoint này trả thông tin service chứ không chạy CLI bật background riêng.

### 8.4 Connect VPN

```text
POST /vpn/{provider}/connect?wait=false
POST /vpn/{provider}/connect?wait=true
POST /vpn/{provider}/connect?wait=true&region=<region>
```

Query params:

| Param | Kiểu | Bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `wait` | bool | Không | Nếu `true`, API chờ tới khi provider báo connected hoặc timeout. |
| `region` | string | Không | Nếu truyền, API set region trước khi connect. |

Ví dụ:

```bash
curl -X POST "http://127.0.0.1:8000/vpn/pia/connect?wait=true"
curl -X POST "http://127.0.0.1:8000/vpn/pia/connect?wait=true&region=vietnam"

curl -X POST "http://127.0.0.1:8000/vpn/hma/connect?wait=true"
curl -X POST "http://127.0.0.1:8000/vpn/hma/connect?wait=true&region=<hma-region-id>"

curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/connect?wait=true"
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/connect?wait=true&region=germany-frankfurt-1"
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "pia",
    "message": "PIA connect command sent",
    "connectionstate": "Connected"
  },
  "warnings": []
}
```

### 8.5 Disconnect VPN

```text
POST /vpn/{provider}/disconnect?wait=false
POST /vpn/{provider}/disconnect?wait=true
```

Ví dụ:

```bash
curl -X POST "http://127.0.0.1:8000/vpn/pia/disconnect?wait=true"
curl -X POST "http://127.0.0.1:8000/vpn/hma/disconnect?wait=true"
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/disconnect?wait=true"
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "expressvpn",
    "message": "ExpressVPN disconnect command sent",
    "connectionstate": "Disconnected"
  },
  "warnings": []
}
```

### 8.6 Get status

```text
GET /vpn/{provider}/status
POST /vpn/{provider}/status
```

Trả trạng thái kết nối, region, public IP và VPN IP nếu đọc được.

Ví dụ:

```bash
curl http://127.0.0.1:8000/vpn/pia/status
curl http://127.0.0.1:8000/vpn/hma/status
curl http://127.0.0.1:8000/vpn/expressvpn/status
```

Response PIA hoặc ExpressVPN mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "expressvpn",
    "connectionstate": "Connected",
    "region": "germany-frankfurt-1",
    "pubip": "203.0.113.10",
    "vpnip": "10.10.10.10"
  },
  "warnings": []
}
```

Response HMA có thêm metadata:

```json
{
  "ok": true,
  "data": {
    "provider": "hma",
    "connectionstate": "connected",
    "raw_connectionstate": "connected",
    "region": "germany-frankfurt",
    "region_available": true,
    "selected_region": "germany-frankfurt",
    "pubip": "203.0.113.20",
    "vpnip": "203.0.113.20",
    "vpnip_source": "publicIpInfo.current.ip when connected",
    "active_gateway": {},
    "connected_location_key": "germany-frankfurt",
    "connectionInfo": {}
  },
  "warnings": []
}
```

### 8.7 Get IP info

```text
GET /vpn/{provider}/ip
POST /vpn/{provider}/ip
```

Ví dụ:

```bash
curl http://127.0.0.1:8000/vpn/pia/ip
curl http://127.0.0.1:8000/vpn/hma/ip
curl http://127.0.0.1:8000/vpn/expressvpn/ip
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "pia",
    "pubip": "118.71.64.61",
    "vpnip": "173.239.247.145"
  },
  "warnings": []
}
```

Ghi chú:

- `pubip` là IP public mà provider CLI hoặc native state đọc được.
- `vpnip` là IP VPN hợp lệ nếu provider đang connected.
- Giá trị như `Unknown`, rỗng, hoặc không phải IP sẽ được normalize thành `null` với warning.

### 8.8 List regions

```text
GET /vpn/{provider}/regions
POST /vpn/{provider}/regions
```

Ví dụ:

```bash
curl http://127.0.0.1:8000/vpn/pia/regions
curl http://127.0.0.1:8000/vpn/hma/regions
curl http://127.0.0.1:8000/vpn/expressvpn/regions
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "expressvpn",
    "regions": [
      "smart",
      "germany-frankfurt-1",
      "usa-new-york"
    ]
  },
  "warnings": []
}
```

### 8.9 Get current region

```text
GET /vpn/{provider}/region
```

Ví dụ:

```bash
curl http://127.0.0.1:8000/vpn/pia/region
curl http://127.0.0.1:8000/vpn/hma/region
curl http://127.0.0.1:8000/vpn/expressvpn/region
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "pia",
    "region": "vietnam"
  },
  "warnings": []
}
```

Nếu provider không có active hoặc selected region:

```json
{
  "ok": true,
  "data": {
    "provider": "hma",
    "region": null,
    "message": "No active or selected VPN region is available for this provider"
  },
  "warnings": []
}
```

### 8.10 Set region

```text
POST /vpn/{provider}/region
```

Body:

```json
{
  "region": "vietnam"
}
```

Ví dụ PIA:

```bash
curl -X POST http://127.0.0.1:8000/vpn/pia/region \
  -H "Content-Type: application/json" \
  -d "{\"region\":\"vietnam\"}"
```

Ví dụ HMA:

```bash
curl -X POST http://127.0.0.1:8000/vpn/hma/region \
  -H "Content-Type: application/json" \
  -d "{\"region\":\"<hma-region-id>\"}"
```

Ví dụ ExpressVPN:

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/region \
  -H "Content-Type: application/json" \
  -d "{\"region\":\"germany-frankfurt-1\"}"
```

Response mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "expressvpn",
    "region": "germany-frankfurt-1",
    "message": "ExpressVPN region updated"
  },
  "warnings": []
}
```

Nếu gọi `POST /vpn/{provider}/region` không có body, API sẽ trả region hiện tại giống `GET /vpn/{provider}/region`.

### 8.11 Refresh IP

```text
POST /vpn/{provider}/refresh-ip
POST /vpn/{provider}/refresh-ip?region=<region>
```

Mục tiêu:

- Giữ provider đang dùng.
- Không truyền `region`: dùng `auto-country`, lấy region hiện tại, suy ra country key, random trong các region cùng country, và ưu tiên region khác region hiện tại nếu có.
- `region=<region>`: dùng `strict-region`, luôn chỉ set và reconnect đúng region đó.
- `region=all`: dùng `all-regions`, random trong toàn bộ region có sẵn của provider.
- `region=<prefix>-`: dùng `prefix-regions`, random trong mọi region bắt đầu bằng prefix đó, ví dụ `usa-` sẽ chọn trong nhóm `usa-*`.
- `region=a|b|c`: dùng `region-list`, random trong các region được liệt kê, ví dụ `usa-chicago|vietnam|singapore-cbd`.
- Nếu country chỉ có 1 region, ví dụ `vietnam`, API vẫn chọn region đó rồi disconnect/connect lại.
- Reconnect VPN.
- Chờ tới khi `after.vpnip` tồn tại và là IP hợp lệ.
- Chỉ thành công nếu `after.vpnip` khác `before.vpnip`.
- Nếu IP sau là `Unknown`, rỗng, invalid, hoặc trùng IP cũ thì tiếp tục retry nếu provider còn attempt.
- Nếu hết timeout hoặc hết số lần thử thì provider có thể trả lỗi HTTP hoặc trả `ok:false` theo chính sách provider.

Ví dụ:

Provider mới sau này nên dùng helper `refresh_region_plan` trong `app.providers.base` để giữ logic này thống nhất.

Nếu dùng danh sách region, nên encode dấu `|` thành `%7C` trong URL.

```bash
curl -X POST http://127.0.0.1:8000/vpn/pia/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/pia/refresh-ip?region=us-seattle"

curl -X POST http://127.0.0.1:8000/vpn/hma/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/hma/refresh-ip?region=<hma-region-id>"

curl -X POST http://127.0.0.1:8000/vpn/expressvpn/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/refresh-ip?region=germany-frankfurt-1"
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/refresh-ip?region=all"
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/refresh-ip?region=usa-"
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/refresh-ip?region=usa-chicago%7Cvietnam%7Csingapore-cbd"
```

Response PIA thành công mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "pia",
    "mode": "auto-country",
    "country_key": "us",
    "requested_region": null,
    "initial_region": "us-new-york",
    "selected_region": "us-seattle",
    "tried_regions": ["us-new-york", "us-seattle"],
    "before": {
      "pubip": "203.0.113.10",
      "vpnip": "10.1.1.10"
    },
    "after": {
      "pubip": "203.0.113.20",
      "vpnip": "10.1.1.20"
    },
    "changed": true,
    "attempts": 2,
    "max_attempts": 0,
    "refresh_timeout_seconds": 180,
    "compare_field": "vpnip",
    "connectionstate": "Connected"
  },
  "warnings": [
    "PIA reconnect does not guarantee a different IP."
  ]
}
```

Response ExpressVPN thành công mẫu:

```json
{
  "ok": true,
  "data": {
    "provider": "expressvpn",
    "mode": "strict-region",
    "country_key": "germany",
    "requested_region": "germany-frankfurt-1",
    "initial_region": "smart",
    "selected_region": "germany-frankfurt-1",
    "tried_regions": ["germany-frankfurt-1"],
    "before": {
      "pubip": "203.0.113.30",
      "vpnip": "10.2.2.30"
    },
    "after": {
      "pubip": "203.0.113.40",
      "vpnip": "10.2.2.40"
    },
    "changed": true,
    "attempts": 1,
    "max_attempts": 0,
    "refresh_timeout_seconds": 180,
    "compare_field": "vpnip",
    "connectionstate": "Connected"
  },
  "warnings": [
    "ExpressVPN reconnect does not guarantee a different IP."
  ]
}
```

Response lỗi khi không có VPN IP trước refresh:

```json
{
  "detail": {
    "error": "Could not read a valid vpnip before refresh",
    "stderr": "{'pubip': '118.71.64.61', 'vpnip': None}"
  }
}
```

## 9. PIA VPN provider

Provider name:

```text
pia
```

Dùng CLI:

```text
C:\Program Files\Private Internet Access\piactl.exe
```

Dùng GUI:

```text
C:\Program Files\Private Internet Access\pia-client.exe
```

Các lệnh CLI được API dùng:

```text
piactl background enable
piactl connect
piactl disconnect
piactl set region <region>
piactl get region
piactl get regions
piactl get connectionstate
piactl get pubip
piactl get vpnip
```

Trạng thái kết nối thường gặp:

```text
Disconnected
Connecting
Connected
Interrupted
Reconnecting
DisconnectingToReconnect
Disconnecting
```

### 9.1 PIA region

PIA region có thể là một region đơn:

```text
vietnam
singapore
```

Hoặc region có nhiều location trong cùng quốc gia:

```text
us-new-york
us-california
us-seattle
us-chicago
```

### 9.2 PIA refresh-ip logic

PIA dùng logic refresh chung như các provider khác:

1. Không truyền `region`:
   - API lấy region hiện tại.
   - Suy ra country key.
   - Nếu region hiện tại là `vietnam`, country key là `vietnam`, chỉ refresh trong `vietnam`.
   - Nếu region hiện tại là `us-new-york`, country key là `us`, API random trong các region `us-*` như `us-seattle`, `us-california`, `us-chicago` và ưu tiên region khác region hiện tại nếu có.

2. Có truyền `region`:
   - `?region=us-seattle` chỉ reconnect trong `us-seattle`.
   - `?region=all` random toàn bộ region của provider.
   - `?region=us-` random mọi region có prefix `us-`.
   - `?region=us-seattle%7Cvietnam%7Csingapore` random một trong các region được liệt kê.

PIA refresh chỉ thành công khi `after.vpnip` hợp lệ và khác `before.vpnip`.

### 9.3 PIA endpoint legacy

Ngoài generic route `/vpn/pia/*`, API vẫn hỗ trợ route riêng:

```text
POST /pia/launch
POST /pia/background/enable
POST /pia/connect?wait=true|false
POST /pia/disconnect?wait=true|false
GET|POST /pia/status
GET|POST /pia/ip
GET|POST /pia/regions
GET /pia/region
POST /pia/region
POST /pia/refresh-ip?region=<optional>
```

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8000/pia/background/enable
curl -X POST http://127.0.0.1:8000/pia/region -H "Content-Type: application/json" -d "{\"region\":\"vietnam\"}"
curl -X POST "http://127.0.0.1:8000/pia/connect?wait=true"
curl http://127.0.0.1:8000/pia/status
curl -X POST http://127.0.0.1:8000/pia/refresh-ip
curl -X POST "http://127.0.0.1:8000/pia/disconnect?wait=true"
```

## 10. HMA VPN provider

Provider name:

```text
hma
```

Dùng native messaging executable:

```text
C:\Program Files\Privax\HMA VPN\VpnNM.exe
```

Dùng GUI:

```text
C:\Program Files\Privax\HMA VPN\Vpn.exe
```

Windows service mặc định:

```text
HmaProVpn
```

HMA provider không dùng CLI text giống PIA hoặc ExpressVPN. Nó gửi native message JSON tới `VpnNM.exe`.

Các action chính:

```text
Vpn_GetState_NmSvc
Vpn_Connect_NmSvc
Vpn_ConnectToOptimal_NmSvc
Vpn_Disconnect_NmSvc
```

### 10.1 HMA region

Region của HMA lấy từ gateway list trong state.

Cách lấy danh sách region:

```bash
curl http://127.0.0.1:8000/vpn/hma/regions
```

Chọn region:

```bash
curl -X POST http://127.0.0.1:8000/vpn/hma/region \
  -H "Content-Type: application/json" \
  -d "{\"region\":\"<hma-region-id>\"}"
```

Sau khi chọn region, lệnh connect tiếp theo sẽ dùng region đó.

Nếu chưa chọn region, HMA sẽ connect optimal location:

```bash
curl -X POST "http://127.0.0.1:8000/vpn/hma/connect?wait=true"
```

### 10.2 HMA status và vpnip

HMA lấy IP từ `publicIpInfo.current.ip` trong state.

Khi connected:

- `pubip` là IP hiện tại từ HMA state.
- `vpnip` cũng lấy từ `publicIpInfo.current.ip`.
- Response có thêm `vpnip_source` để nói rõ nguồn dữ liệu.

### 10.3 HMA refresh-ip logic

HMA refresh yêu cầu đang connected.

Nếu chưa connected, API trả 409:

```json
{
  "detail": {
    "error": "HMA refresh-ip requires an active VPN connection. Use /vpn/hma/connect first.",
    "stderr": "connectionstate=disconnected"
  }
}
```

HMA cũng dùng logic refresh chung:

- Không truyền `region`: dùng `auto-country`, random trong các gateway cùng country với region hiện tại.
- `region=<gateway-id>`: dùng `strict-region`, chỉ reconnect đúng gateway đó.
- `region=all`: random toàn bộ gateway.
- `region=<prefix>-`: random mọi gateway có prefix đó.
- `region=a|b|c`: random một gateway trong danh sách được truyền.
- Nếu country chỉ có 1 gateway, API vẫn chọn gateway đó rồi disconnect/connect lại.

Mặc định:

```env
HMA_REFRESH_MAX_ATTEMPTS=1
HMA_REFRESH_TIMEOUT_SECONDS=180
```

Nghĩa là HMA chỉ reconnect 1 lần theo cấu hình mặc định. Nếu muốn thử nhiều gateway trong cùng country khi IP chưa đổi, tăng `HMA_REFRESH_MAX_ATTEMPTS` trong `.env`.

Ví dụ refresh:

```bash
curl -X POST http://127.0.0.1:8000/vpn/hma/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/hma/refresh-ip?region=<hma-region-id>"
```

## 11. ExpressVPN provider

Provider name:

```text
expressvpn
```

Dùng CLI:

```text
C:\Program Files\ExpressVPN\expressvpnctl.exe
```

Dùng GUI:

```text
C:\Program Files\ExpressVPN\expressvpn-client.exe
```

Các lệnh CLI được API dùng:

```text
expressvpnctl background enable
expressvpnctl connect
expressvpnctl disconnect
expressvpnctl set region <region>
expressvpnctl get region
expressvpnctl get regions
expressvpnctl get connectionstate
expressvpnctl get pubip
expressvpnctl get vpnip
```

Theo help của ExpressVPN CLI, một số lệnh như `connect` cần GUI client đang chạy hoặc background mode đã bật. Vì vậy nên chạy:

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/background/enable
```

hoặc mở GUI:

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/launch
```

trước khi connect.

### 11.1 ExpressVPN region

ExpressVPN hỗ trợ region như:

```text
smart
germany-frankfurt-1
```

Lấy danh sách region:

```bash
curl http://127.0.0.1:8000/vpn/expressvpn/regions
```

Chọn region:

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/region \
  -H "Content-Type: application/json" \
  -d "{\"region\":\"germany-frankfurt-1\"}"
```

Connect vào region cụ thể bằng query param:

```bash
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/connect?wait=true&region=germany-frankfurt-1"
```

### 11.2 ExpressVPN refresh-ip logic

ExpressVPN cũng dùng logic refresh chung:

- Không truyền `region`: dùng `auto-country`, random trong các region cùng country với region hiện tại.
- `region=<region>`: dùng `strict-region`, chỉ set và reconnect đúng region đó.
- `region=all`: random toàn bộ region.
- `region=<prefix>-`: random mọi region có prefix đó, ví dụ `usa-`.
- `region=a|b|c`: random một region trong danh sách được truyền.
- Nếu country chỉ có 1 region, API vẫn chọn region đó rồi disconnect/connect lại.
- `before.vpnip` phải tồn tại và hợp lệ.
- `after.vpnip` phải tồn tại, hợp lệ, và khác IP cũ.
- Giá trị `Unknown` từ `expressvpnctl get vpnip` không được coi là IP.
- Mặc định retry tới khi đổi IP hoặc hết 180 giây.

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/refresh-ip?region=germany-frankfurt-1"
```

## 12. Quy trình sử dụng khuyến nghị

### 12.1 PIA

```bash
curl -X POST http://127.0.0.1:8000/vpn/pia/background/enable
curl http://127.0.0.1:8000/vpn/pia/regions
curl -X POST http://127.0.0.1:8000/vpn/pia/region -H "Content-Type: application/json" -d "{\"region\":\"vietnam\"}"
curl -X POST "http://127.0.0.1:8000/vpn/pia/connect?wait=true"
curl http://127.0.0.1:8000/vpn/pia/status
curl -X POST http://127.0.0.1:8000/vpn/pia/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/pia/disconnect?wait=true"
```

### 12.2 HMA

```bash
curl -X POST http://127.0.0.1:8000/vpn/hma/launch
curl http://127.0.0.1:8000/vpn/hma/regions
curl -X POST "http://127.0.0.1:8000/vpn/hma/connect?wait=true"
curl http://127.0.0.1:8000/vpn/hma/status
curl -X POST http://127.0.0.1:8000/vpn/hma/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/hma/disconnect?wait=true"
```

### 12.3 ExpressVPN

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/background/enable
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/launch
curl http://127.0.0.1:8000/vpn/expressvpn/regions
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/region -H "Content-Type: application/json" -d "{\"region\":\"germany-frankfurt-1\"}"
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/connect?wait=true"
curl http://127.0.0.1:8000/vpn/expressvpn/status
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/refresh-ip
curl -X POST "http://127.0.0.1:8000/vpn/expressvpn/disconnect?wait=true"
```

## 13. Kiểm tra nhanh từ Python

Compile source:

```bash
python -m compileall -q app
```

Import app:

```bash
PYTHONPATH=. python -c "from app.main import app; print(app.title)"
```

Kiểm tra provider registry:

```bash
PYTHONPATH=. python -c "from app.config import get_settings; from app.providers.registry import get_provider; print(type(get_provider('pia', get_settings())).__name__)"
PYTHONPATH=. python -c "from app.config import get_settings; from app.providers.registry import get_provider; print(type(get_provider('hma', get_settings())).__name__)"
PYTHONPATH=. python -c "from app.config import get_settings; from app.providers.registry import get_provider; print(type(get_provider('expressvpn', get_settings())).__name__)"
```

## 14. Ghi chú bảo mật

- Mặc định nên bind API vào `127.0.0.1`, không bind `0.0.0.0` nếu không thật sự cần.
- Nếu mở API cho máy khác trong LAN, nên đặt `API_KEY`.
- API này có quyền connect, disconnect và đổi VPN region trên máy Windows, vì vậy không nên public ra Internet.
- Không truyền secret hoặc tài khoản VPN qua query string.
- API hiện không login provider. Bạn cần login sẵn trong app VPN hoặc dùng CLI chính thức của provider nếu cần login.

## 15. Troubleshooting

### Không tìm thấy executable

Lỗi thường gặp:

```json
{
  "detail": {
    "error": "ExpressVPN CLI executable was not found",
    "stderr": "C:\\Program Files\\ExpressVPN\\expressvpnctl.exe"
  }
}
```

Cách xử lý:

- Kiểm tra app VPN đã cài chưa.
- Kiểm tra path thật trên máy.
- Override path trong `.env`.

### ExpressVPN connect báo lỗi cần GUI hoặc background

Chạy một trong hai lệnh:

```bash
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/background/enable
curl -X POST http://127.0.0.1:8000/vpn/expressvpn/launch
```

Sau đó connect lại.

### Refresh IP bị timeout

Nguyên nhân thường gặp:

- Provider reconnect xong nhưng vẫn cấp lại cùng IP.
- Provider trả `Unknown` hoặc chưa có `vpnip` sau connect.
- Network chưa ổn định.
- Timeout quá ngắn.

Cách xử lý:

- Tăng `*_REFRESH_TIMEOUT_SECONDS`.
- Với HMA, tăng `HMA_REFRESH_MAX_ATTEMPTS` nếu muốn retry nhiều hơn 1 lần.
- Với PIA, thử truyền region cụ thể nếu muốn strict region, ví dụ `?region=us-seattle`.
- Với ExpressVPN, thử truyền region cụ thể, ví dụ `?region=germany-frankfurt-1`.

### API key bị từ chối

Nếu có `API_KEY`, mọi request VPN cần header:

```bash
-H "X-API-Key: <your-api-key>"
```

Nếu đang test local và không muốn auth, để:

```env
API_KEY=
```
