<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class LicenseDailyUsage extends Model
{
    public $timestamps = false;

    protected $table = 'license_daily_usage';

    protected $fillable = [
        'license_id',
        'usage_date',
        'search_count',
    ];

    protected function casts(): array
    {
        return [
            'usage_date' => 'date',
            'search_count' => 'integer',
        ];
    }

    public function license(): BelongsTo
    {
        return $this->belongsTo(License::class);
    }
}
