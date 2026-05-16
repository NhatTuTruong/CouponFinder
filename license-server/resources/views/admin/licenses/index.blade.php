@extends('layouts.admin')

@section('title', 'Quản lý License')

@section('content')
<div class="api-hint">
    Tool Coupon Finder kết nối qua URL server (ví dụ <code>http://127.0.0.1:8080</code>) và gọi API:
    <code>POST /api/v1/license/activate</code>,
    <code>POST /api/v1/license/consume</code>.
    Đặt <code>COUPON_FINDER_LICENSE_SERVER_URL</code> trong file <code>.env</code> của tool.
</div>

<section class="card">
    <h2>Thêm license mới</h2>
    <form method="post" action="{{ route('admin.licenses.store') }}">
        @csrf
        <div class="form-grid">
            <div>
                <label for="license_key">Key bản quyền</label>
                <div class="key-row">
                    <input type="text" id="license_key" name="license_key" value="{{ old('license_key', $generatedKey) }}" required maxlength="64">
                    <button type="button" class="btn btn-orange" id="btn-generate-key">Tạo</button>
                </div>
            </div>
            <div>
                <label for="daily_search_limit">Giới hạn record/ngày</label>
                <input type="number" id="daily_search_limit" name="daily_search_limit" value="{{ old('daily_search_limit', 500) }}" min="1" required>
            </div>
            <div>
                <label for="max_machines">Số máy tối đa</label>
                <input type="number" id="max_machines" name="max_machines" value="{{ old('max_machines', 2) }}" min="1" max="100" required>
            </div>
            <div>
                <label for="expires_at">Hạn dùng</label>
                <input type="datetime-local" id="expires_at" name="expires_at" value="{{ old('expires_at') }}">
            </div>
            <div class="full">
                <label for="notes">Ghi chú</label>
                <textarea id="notes" name="notes" placeholder="Mô tả khách hàng, gói, …">{{ old('notes') }}</textarea>
            </div>
            <div>
                <label><input type="checkbox" name="is_active" value="1" checked> Đang hoạt động</label>
            </div>
            <div>
                <button type="submit" class="btn btn-primary">Tạo license</button>
            </div>
        </div>
    </form>
</section>

<section class="card">
    <h2>Danh sách license</h2>
    <p class="muted table-hint">Sửa trực tiếp các ô bên dưới rồi bấm <strong>Lưu</strong> trên từng dòng.</p>
    <div class="table-wrap">
        <table class="license-table">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Record/ngày</th>
                    <th>Số máy tối đa</th>
                    <th>Đã dùng hôm nay</th>
                    <th>Máy đăng ký</th>
                    <th>Hạn dùng</th>
                    <th>Ghi chú</th>
                    <th>Trạng thái</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
            @forelse($licenses as $license)
                @php
                    $formId = 'lic-form-' . $license->id;
                    $usedToday = (int) ($usageToday[$license->id] ?? 0);
                @endphp
                <tr>
                    <td class="col-key"><code>{{ $license->license_key }}</code></td>
                    <td>
                        <input form="{{ $formId }}" type="number" name="daily_search_limit"
                               value="{{ $license->daily_search_limit }}" min="1" class="input-sm" required>
                    </td>
                    <td>
                        <input form="{{ $formId }}" type="number" name="max_machines"
                               value="{{ $license->max_machines }}" min="1" max="100" class="input-sm" required>
                    </td>
                    <td class="col-used">
                        <span class="{{ $usedToday >= $license->daily_search_limit ? 'text-danger' : '' }}">
                            {{ $usedToday }}
                        </span>
                        <span class="muted">/ {{ $license->daily_search_limit }}</span>
                    </td>
                    <td class="muted">{{ $license->machines_count }}</td>
                    <td>
                        <input form="{{ $formId }}" type="datetime-local" name="expires_at"
                               value="{{ $license->expiresAtForInput() }}" class="input-sm input-datetime">
                    </td>
                    <td>
                        <input form="{{ $formId }}" type="text" name="notes"
                               value="{{ $license->notes }}" class="input-sm input-notes" placeholder="Ghi chú">
                    </td>
                    <td class="col-active">
                        <input form="{{ $formId }}" type="hidden" name="is_active" value="0">
                        <label class="checkbox-inline">
                            <input form="{{ $formId }}" type="checkbox" name="is_active" value="1"
                                   @checked($license->is_active && !$license->isExpired())>
                            Hoạt động
                        </label>
                        @if($license->isExpired())
                            <span class="badge badge-off">Hết hạn</span>
                        @endif
                    </td>
                    <td class="col-actions">
                        <form id="{{ $formId }}" method="post" action="{{ route('admin.licenses.update', $license) }}">
                            @csrf
                            @method('PUT')
                            <button type="submit" class="btn btn-primary btn-sm">Lưu</button>
                        </form>
                        <form method="post" action="{{ route('admin.licenses.destroy', $license) }}"
                              onsubmit="return confirm('Xóa license {{ $license->license_key }}?')">
                            @csrf
                            @method('DELETE')
                            <button type="submit" class="btn btn-danger btn-sm">Xóa</button>
                        </form>
                    </td>
                </tr>
            @empty
                <tr><td colspan="9" class="muted">Chưa có license.</td></tr>
            @endforelse
            </tbody>
        </table>
    </div>
    {{ $licenses->links() }}
</section>

@push('head')
<script>
document.getElementById('btn-generate-key')?.addEventListener('click', async () => {
    const res = await fetch('{{ route('admin.licenses.generate-key') }}');
    const data = await res.json();
    if (data.key) document.getElementById('license_key').value = data.key;
});
</script>
@endpush
@endsection
