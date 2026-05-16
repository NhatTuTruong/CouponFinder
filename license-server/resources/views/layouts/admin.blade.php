<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>@yield('title', 'Coupon Finder License')</title>
    <style>
        :root {
            --bg: #f4f6f9;
            --card: #fff;
            --border: #e2e8f0;
            --text: #1e293b;
            --muted: #64748b;
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --danger: #dc2626;
            --orange: #ea580c;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: "Segoe UI", system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            font-size: 14px;
        }
        .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
        h1 { font-size: 1.35rem; margin: 0 0 20px; }
        .card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,.04);
        }
        .card h2 { font-size: 1rem; margin: 0 0 16px; font-weight: 600; }
        .form-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px 16px;
            align-items: end;
        }
        .form-grid .full { grid-column: 1 / -1; }
        label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
        input[type="text"], input[type="number"], input[type="datetime-local"], textarea {
            width: 100%;
            padding: 8px 10px;
            border: 1px solid var(--border);
            border-radius: 6px;
            font-size: 14px;
        }
        textarea { min-height: 60px; resize: vertical; }
        .key-row { display: flex; gap: 8px; }
        .key-row input { flex: 1; }
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 8px 14px;
            border-radius: 6px;
            border: none;
            font-size: 13px;
            cursor: pointer;
            text-decoration: none;
        }
        .btn-primary { background: var(--primary); color: #fff; }
        .btn-primary:hover { background: var(--primary-hover); }
        .btn-orange { background: var(--orange); color: #fff; }
        .btn-orange:hover { filter: brightness(.95); }
        .btn-danger { background: var(--danger); color: #fff; }
        .btn-ghost { background: #f1f5f9; color: var(--text); border: 1px solid var(--border); }
        .flash { padding: 10px 14px; border-radius: 6px; margin-bottom: 16px; background: #dcfce7; color: #166534; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px 8px; text-align: left; border-bottom: 1px solid var(--border); }
        th { font-size: 12px; color: var(--muted); font-weight: 600; }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 11px;
        }
        .badge-ok { background: #dcfce7; color: #166534; }
        .badge-off { background: #fee2e2; color: #991b1b; }
        .muted { color: var(--muted); font-size: 12px; }
        .api-hint {
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 12px 14px;
            margin-bottom: 20px;
            font-size: 13px;
        }
        .api-hint code { background: #dbeafe; padding: 2px 6px; border-radius: 4px; }
        @media (max-width: 900px) {
            .form-grid { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 600px) {
            .form-grid { grid-template-columns: 1fr; }
        }
        .table-hint { margin: 0 0 12px; font-size: 13px; }
        .table-wrap { overflow-x: auto; }
        .license-table { min-width: 960px; }
        .license-table .input-sm {
            width: 100%;
            min-width: 72px;
            padding: 6px 8px;
            font-size: 13px;
        }
        .license-table .input-datetime { min-width: 170px; }
        .license-table .input-notes { min-width: 140px; }
        .license-table .col-key code { font-size: 11px; word-break: break-all; }
        .license-table .col-actions {
            white-space: nowrap;
            vertical-align: middle;
        }
        .license-table .col-actions form {
            display: inline-block;
            margin: 2px 0;
        }
        .btn-sm { padding: 5px 10px; font-size: 12px; }
        .checkbox-inline {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            white-space: nowrap;
        }
        .text-danger { color: var(--danger); font-weight: 600; }
        .col-used { white-space: nowrap; }
        .header-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 20px;
        }
        .header-row h1 { margin: 0; }
    </style>
    @stack('head')
</head>
<body>
<div class="wrap">
    <div class="header-row">
        <h1>Coupon Finder — Quản lý License</h1>
        <form method="post" action="{{ route('admin.logout') }}">
            @csrf
            <button type="submit" class="btn btn-ghost">Đăng xuất</button>
        </form>
    </div>
    @if(session('success'))
        <div class="flash">{{ session('success') }}</div>
    @endif
    @yield('content')
</div>
</body>
</html>
