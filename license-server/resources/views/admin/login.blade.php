<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Đăng nhập — Coupon Finder License</title>
    <style>
        :root {
            --bg: #f4f6f9;
            --card: #fff;
            --border: #e2e8f0;
            --text: #1e293b;
            --muted: #64748b;
            --primary: #2563eb;
            --danger: #dc2626;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Segoe UI", system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
        }
        .card {
            width: 100%;
            max-width: 380px;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 28px 24px;
            box-shadow: 0 4px 24px rgba(0,0,0,.06);
        }
        h1 { font-size: 1.2rem; margin: 0 0 8px; }
        p { margin: 0 0 20px; color: var(--muted); font-size: 14px; }
        label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
        input[type="password"] {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid var(--border);
            border-radius: 8px;
            font-size: 15px;
        }
        .btn {
            width: 100%;
            margin-top: 16px;
            padding: 10px;
            border: none;
            border-radius: 8px;
            background: var(--primary);
            color: #fff;
            font-size: 15px;
            cursor: pointer;
        }
        .btn:hover { filter: brightness(.95); }
        .error {
            margin-top: 12px;
            padding: 8px 10px;
            border-radius: 6px;
            background: #fee2e2;
            color: #991b1b;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Coupon Finder License</h1>
        <p>Đăng nhập quản trị</p>
        <form method="post" action="{{ route('admin.login.submit') }}">
            @csrf
            <label for="password">Mật khẩu</label>
            <input type="password" id="password" name="password" required autofocus autocomplete="current-password">
            <button type="submit" class="btn">Đăng nhập</button>
        </form>
        @error('password')
            <div class="error">{{ $message }}</div>
        @enderror
    </div>
</body>
</html>
