@if ($paginator->hasPages())
    <nav class="pagination-bar" aria-label="Phân trang danh sách license">
        <div class="pagination-meta muted">
            Hiển thị {{ $paginator->firstItem() ?? 0 }}–{{ $paginator->lastItem() ?? 0 }}
            / {{ $paginator->total() }} license
        </div>
        <div class="pagination-links">
            @if ($paginator->onFirstPage())
                <span class="page-btn disabled">Trước</span>
            @else
                <a class="page-btn" href="{{ $paginator->previousPageUrl() }}" rel="prev">Trước</a>
            @endif

            @foreach ($elements as $element)
                @if (is_string($element))
                    <span class="page-ellipsis">…</span>
                @endif
                @if (is_array($element))
                    @foreach ($element as $page => $url)
                        @if ($page == $paginator->currentPage())
                            <span class="page-btn active" aria-current="page">{{ $page }}</span>
                        @else
                            <a class="page-btn" href="{{ $url }}">{{ $page }}</a>
                        @endif
                    @endforeach
                @endif
            @endforeach

            @if ($paginator->hasMorePages())
                <a class="page-btn" href="{{ $paginator->nextPageUrl() }}" rel="next">Sau</a>
            @else
                <span class="page-btn disabled">Sau</span>
            @endif
        </div>
    </nav>
@elseif ($paginator->total() > 0)
    <div class="pagination-bar">
        <div class="pagination-meta muted">Tổng {{ $paginator->total() }} license</div>
    </div>
@endif
