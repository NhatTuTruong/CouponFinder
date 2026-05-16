<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\LicenseService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ToolLicenseController extends Controller
{
    public function __construct(private readonly LicenseService $licenses) {}

    public function activate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:64'],
            'machine_id' => ['required', 'string', 'max:128'],
            'machine_label' => ['nullable', 'string', 'max:255'],
        ]);

        $result = $this->licenses->activate(
            $data['license_key'],
            $data['machine_id'],
            $data['machine_label'] ?? null,
        );

        return response()->json($result, $result['ok'] ? 200 : 403);
    }

    public function status(Request $request): JsonResponse
    {
        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:64'],
            'machine_id' => ['required', 'string', 'max:128'],
        ]);

        $license = $this->licenses->findActiveLicense($data['license_key']);
        if ($license === null) {
            return response()->json(['ok' => false, 'message' => 'Mã license không hợp lệ.'], 403);
        }

        if ($license->isExpired()) {
            return response()->json(['ok' => false, 'message' => 'License đã hết hạn.'], 403);
        }

        $payload = $this->licenses->statusPayload(
            $license,
            trim($data['machine_id']),
            'OK',
        );

        return response()->json($payload);
    }

    public function consume(Request $request): JsonResponse
    {
        $data = $request->validate([
            'license_key' => ['required', 'string', 'max:64'],
            'machine_id' => ['required', 'string', 'max:128'],
            'count' => ['nullable', 'integer', 'min:1', 'max:100'],
        ]);

        $result = $this->licenses->consume(
            $data['license_key'],
            $data['machine_id'],
            (int) ($data['count'] ?? 1),
        );

        return response()->json($result, $result['ok'] ? 200 : 403);
    }
}
