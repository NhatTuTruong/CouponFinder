<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\License;
use App\Models\LicenseDailyUsage;
use App\Models\LicenseMachine;
use Carbon\Carbon;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;

class LicenseAdminController extends Controller
{
    public function index(): View
    {
        $licenses = License::query()
            ->withCount('machines')
            ->orderByDesc('id')
            ->paginate(20);

        $today = Carbon::today()->toDateString();
        $usageToday = LicenseDailyUsage::query()
            ->where('usage_date', $today)
            ->pluck('search_count', 'license_id');

        return view('admin.licenses.index', [
            'licenses' => $licenses,
            'generatedKey' => License::generateKey(),
            'usageToday' => $usageToday,
        ]);
    }

    public function store(Request $request): RedirectResponse
    {
        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:64', 'unique:licenses,license_key'],
            'daily_search_limit' => ['required', 'integer', 'min:1', 'max:1000000'],
            'max_machines' => ['required', 'integer', 'min:1', 'max:100'],
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
            'is_active' => ['nullable', 'boolean'],
        ]);

        License::query()->create([
            'license_key' => strtoupper(trim($data['license_key'])),
            'daily_search_limit' => $data['daily_search_limit'],
            'max_machines' => $data['max_machines'],
            'expires_at' => $request->filled('expires_at') ? $request->date('expires_at') : null,
            'notes' => $data['notes'] ?? null,
            'is_active' => $request->boolean('is_active', true),
        ]);

        return redirect()->route('admin.licenses.index')
            ->with('success', 'Đã tạo license.');
    }

    public function update(Request $request, License $license): RedirectResponse
    {
        $data = $request->validate([
            'daily_search_limit' => ['required', 'integer', 'min:1', 'max:1000000'],
            'max_machines' => ['required', 'integer', 'min:1', 'max:100'],
            'expires_at' => ['nullable', 'date'],
            'notes' => ['nullable', 'string', 'max:2000'],
            'is_active' => ['nullable', 'boolean'],
        ]);

        $license->update([
            'daily_search_limit' => $data['daily_search_limit'],
            'max_machines' => $data['max_machines'],
            'expires_at' => $request->filled('expires_at') ? $request->date('expires_at') : null,
            'notes' => $data['notes'] ?? null,
            'is_active' => $request->boolean('is_active'),
        ]);

        return redirect()->route('admin.licenses.index')
            ->with('success', "Đã cập nhật license {$license->license_key}.");
    }

    public function destroy(License $license): RedirectResponse
    {
        $license->delete();

        return redirect()->route('admin.licenses.index')
            ->with('success', 'Đã xóa license.');
    }

    public function removeMachine(License $license, LicenseMachine $machine): RedirectResponse
    {
        if ($machine->license_id !== $license->id) {
            abort(404);
        }
        $machine->delete();

        return redirect()->route('admin.licenses.index')
            ->with('success', 'Đã gỡ máy khỏi license.');
    }

    public function generateKey(): \Illuminate\Http\JsonResponse
    {
        return response()->json(['key' => License::generateKey()]);
    }
}
