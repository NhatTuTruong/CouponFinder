<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Str;

class License extends Model
{
    protected $fillable = [
        'license_key',
        'daily_search_limit',
        'max_machines',
        'expires_at',
        'notes',
        'is_active',
    ];

    protected function casts(): array
    {
        return [
            'expires_at' => 'datetime',
            'is_active' => 'boolean',
            'daily_search_limit' => 'integer',
            'max_machines' => 'integer',
        ];
    }

    public static function generateKey(): string
    {
        return strtoupper(Str::replace('-', '', (string) Str::uuid()));
    }

    public function machines(): HasMany
    {
        return $this->hasMany(LicenseMachine::class);
    }

    public function dailyUsage(): HasMany
    {
        return $this->hasMany(LicenseDailyUsage::class);
    }

    public function isExpired(): bool
    {
        return $this->expires_at !== null && $this->expires_at->isPast();
    }

    public function expiresAtForInput(): string
    {
        if ($this->expires_at === null) {
            return '';
        }

        return $this->expires_at->format('Y-m-d\TH:i');
    }
}
