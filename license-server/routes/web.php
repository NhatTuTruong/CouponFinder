<?php

use App\Http\Controllers\Admin\AdminLoginController;
use App\Http\Controllers\Admin\LicenseAdminController;
use Illuminate\Support\Facades\Route;

Route::redirect('/', '/admin/login');

Route::prefix('admin')->name('admin.')->group(function () {
    Route::get('/login', [AdminLoginController::class, 'show'])->name('login');
    Route::post('/login', [AdminLoginController::class, 'login'])->name('login.submit');

    Route::middleware('admin.auth')->group(function () {
        Route::post('/logout', [AdminLoginController::class, 'logout'])->name('logout');
        Route::get('/licenses', [LicenseAdminController::class, 'index'])->name('licenses.index');
        Route::post('/licenses', [LicenseAdminController::class, 'store'])->name('licenses.store');
        Route::put('/licenses/{license}', [LicenseAdminController::class, 'update'])->name('licenses.update');
        Route::delete('/licenses/{license}', [LicenseAdminController::class, 'destroy'])->name('licenses.destroy');
        Route::delete('/licenses/{license}/machines/{machine}', [LicenseAdminController::class, 'removeMachine'])
            ->name('licenses.machines.destroy');
        Route::get('/licenses/generate-key', [LicenseAdminController::class, 'generateKey'])->name('licenses.generate-key');
    });
});
