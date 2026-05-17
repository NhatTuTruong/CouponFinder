@if(request('q'))
    <input type="hidden" name="return_q" value="{{ request('q') }}">
@endif
@if(request('page'))
    <input type="hidden" name="return_page" value="{{ request('page') }}">
@endif
@if(request('per_page'))
    <input type="hidden" name="return_per_page" value="{{ request('per_page') }}">
@endif
