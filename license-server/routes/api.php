<?php

use App\Http\Controllers\Api\ToolLicenseController;
use Illuminate\Support\Facades\Route;

Route::prefix('v1')->group(function () {
    Route::post('/license/activate', [ToolLicenseController::class, 'activate']);
    Route::post('/license/status', [ToolLicenseController::class, 'status']);
    Route::post('/license/consume', [ToolLicenseController::class, 'consume']);
});
