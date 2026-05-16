<?php

namespace App\Services;

use App\Models\License;
use App\Models\LicenseDailyUsage;
use App\Models\LicenseMachine;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;

class LicenseService
{
    /**
     * @return array{ok: bool, message: string, license?: License, machines_count?: int, searches_today?: int, searches_remaining?: int}
     */
    public function activate(string $licenseKey, string $machineId, ?string $machineLabel = null): array
    {
        $license = $this->findActiveLicense($licenseKey);
        if ($license === null) {
            return ['ok' => false, 'message' => 'Mã license không hợp lệ hoặc đã bị vô hiệu hóa.'];
        }

        if ($license->isExpired()) {
            return ['ok' => false, 'message' => 'License đã hết hạn.'];
        }

        $machineId = trim($machineId);
        if ($machineId === '') {
            return ['ok' => false, 'message' => 'machine_id không hợp lệ.'];
        }

        return DB::transaction(function () use ($license, $machineId, $machineLabel) {
            $now = now();
            $machine = LicenseMachine::query()
                ->where('license_id', $license->id)
                ->where('machine_id', $machineId)
                ->lockForUpdate()
                ->first();

            if ($machine) {
                $machine->last_seen_at = $now;
                if ($machineLabel) {
                    $machine->machine_label = $machineLabel;
                }
                $machine->save();
            } else {
                $count = LicenseMachine::query()
                    ->where('license_id', $license->id)
                    ->lockForUpdate()
                    ->count();

                if ($count >= $license->max_machines) {
                    return [
                        'ok' => false,
                        'message' => "Đã đạt số máy tối đa ({$license->max_machines}). Liên hệ admin để gỡ máy cũ.",
                    ];
                }

                LicenseMachine::query()->create([
                    'license_id' => $license->id,
                    'machine_id' => $machineId,
                    'machine_label' => $machineLabel,
                    'first_seen_at' => $now,
                    'last_seen_at' => $now,
                ]);
            }

            return $this->statusPayload($license, $machineId, 'Kích hoạt thành công.');
        });
    }

    /**
     * @return array{ok: bool, message: string, consumed?: int}
     */
    public function consume(string $licenseKey, string $machineId, int $count = 1): array
    {
        if ($count < 1) {
            return ['ok' => false, 'message' => 'Số lượt không hợp lệ.'];
        }

        $license = $this->findActiveLicense($licenseKey);
        if ($license === null) {
            return ['ok' => false, 'message' => 'Mã license không hợp lệ.'];
        }

        if ($license->isExpired()) {
            return ['ok' => false, 'message' => 'License đã hết hạn.'];
        }

        $machineId = trim($machineId);
        $registered = LicenseMachine::query()
            ->where('license_id', $license->id)
            ->where('machine_id', $machineId)
            ->exists();

        if (! $registered) {
            $activate = $this->activate($licenseKey, $machineId);
            if (! $activate['ok']) {
                return $activate;
            }
        }

        return DB::transaction(function () use ($license, $machineId, $count) {
            $today = Carbon::today()->toDateString();
            $usage = LicenseDailyUsage::query()
                ->where('license_id', $license->id)
                ->where('usage_date', $today)
                ->lockForUpdate()
                ->first();

            $used = $usage?->search_count ?? 0;
            if ($used + $count > $license->daily_search_limit) {
                $remaining = max(0, $license->daily_search_limit - $used);

                return [
                    'ok' => false,
                    'message' => "Đã hết lượt tìm kiếm hôm nay (còn {$remaining}/{$license->daily_search_limit}).",
                    'searches_today' => $used,
                    'searches_remaining' => $remaining,
                    'daily_search_limit' => $license->daily_search_limit,
                ];
            }

            if ($usage) {
                $usage->search_count = $used + $count;
                $usage->save();
            } else {
                LicenseDailyUsage::query()->create([
                    'license_id' => $license->id,
                    'usage_date' => $today,
                    'search_count' => $count,
                ]);
            }

            LicenseMachine::query()
                ->where('license_id', $license->id)
                ->where('machine_id', $machineId)
                ->update(['last_seen_at' => now()]);

            $newUsed = $used + $count;

            return array_merge(
                $this->statusPayload($license, $machineId, 'OK'),
                [
                    'ok' => true,
                    'consumed' => $count,
                    'searches_today' => $newUsed,
                    'searches_remaining' => $license->daily_search_limit - $newUsed,
                ]
            );
        });
    }

    /**
     * @return array<string, mixed>
     */
    public function statusPayload(License $license, string $machineId, string $message): array
    {
        $today = Carbon::today()->toDateString();
        $used = (int) LicenseDailyUsage::query()
            ->where('license_id', $license->id)
            ->where('usage_date', $today)
            ->value('search_count');

        $machinesCount = LicenseMachine::query()
            ->where('license_id', $license->id)
            ->count();

        return [
            'ok' => true,
            'message' => $message,
            'license_key' => $license->license_key,
            'daily_search_limit' => $license->daily_search_limit,
            'max_machines' => $license->max_machines,
            'machines_count' => $machinesCount,
            'searches_today' => $used,
            'searches_remaining' => max(0, $license->daily_search_limit - $used),
            'expires_at' => $license->expires_at?->toIso8601String(),
            'machine_registered' => LicenseMachine::query()
                ->where('license_id', $license->id)
                ->where('machine_id', $machineId)
                ->exists(),
        ];
    }

    public function findActiveLicense(string $licenseKey): ?License
    {
        $key = strtoupper(trim($licenseKey));

        return License::query()
            ->where('license_key', $key)
            ->where('is_active', true)
            ->first();
    }
}
