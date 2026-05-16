<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('licenses', function (Blueprint $table) {
            $table->id();
            $table->string('license_key', 64)->unique();
            $table->unsignedInteger('daily_search_limit')->default(500);
            $table->unsignedSmallInteger('max_machines')->default(2);
            $table->timestamp('expires_at')->nullable();
            $table->text('notes')->nullable();
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });

        Schema::create('license_machines', function (Blueprint $table) {
            $table->id();
            $table->foreignId('license_id')->constrained('licenses')->cascadeOnDelete();
            $table->string('machine_id', 128);
            $table->string('machine_label', 255)->nullable();
            $table->timestamp('first_seen_at');
            $table->timestamp('last_seen_at');
            $table->unique(['license_id', 'machine_id']);
        });

        Schema::create('license_daily_usage', function (Blueprint $table) {
            $table->id();
            $table->foreignId('license_id')->constrained('licenses')->cascadeOnDelete();
            $table->date('usage_date');
            $table->unsignedInteger('search_count')->default(0);
            $table->unique(['license_id', 'usage_date']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('license_daily_usage');
        Schema::dropIfExists('license_machines');
        Schema::dropIfExists('licenses');
    }
};
