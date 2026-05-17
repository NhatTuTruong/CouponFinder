<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Phục hồi khi migrate lỗi giữa chừng: bảng `licenses` đã tạo nhưng `license_machines` chưa.
 * Dùng DATETIME nullable (không dùng TIMESTAMP).
 */
return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('licenses')) {
            return;
        }

        if (! Schema::hasTable('license_machines')) {
            Schema::create('license_machines', function (Blueprint $table) {
                $table->id();
                $table->foreignId('license_id')->constrained('licenses')->cascadeOnDelete();
                $table->string('machine_id', 128);
                $table->string('machine_label', 255)->nullable();
                $table->dateTime('first_seen_at')->nullable();
                $table->dateTime('last_seen_at')->nullable();
                $table->unique(['license_id', 'machine_id']);
            });
        }

        if (! Schema::hasTable('license_daily_usage')) {
            Schema::create('license_daily_usage', function (Blueprint $table) {
                $table->id();
                $table->foreignId('license_id')->constrained('licenses')->cascadeOnDelete();
                $table->date('usage_date');
                $table->unsignedInteger('search_count')->default(0);
                $table->unique(['license_id', 'usage_date']);
            });
        }
    }

    public function down(): void
    {
        // Không drop — migration phục hồi; rollback dùng migration gốc.
    }
};
