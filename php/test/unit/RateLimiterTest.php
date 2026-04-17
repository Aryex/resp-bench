<?php

declare(strict_types=1);

namespace RespBench\Tests\Unit;

use PHPUnit\Framework\TestCase;
use RespBench\Engine\RateLimiter;

class RateLimiterTest extends TestCase
{
    public function testCreateReturnsNullForZeroRate(): void
    {
        $this->assertNull(RateLimiter::create(0));
        $this->assertNull(RateLimiter::create(-1));
    }

    public function testCreateReturnsInstanceForPositiveRate(): void
    {
        $limiter = RateLimiter::create(100);
        $this->assertInstanceOf(RateLimiter::class, $limiter);
    }

    public function testAcquireReturnsImmediatelyForFirstCall(): void
    {
        $limiter = RateLimiter::create(1000);
        $start = hrtime(true);
        $limiter->acquire();
        $elapsed = (hrtime(true) - $start) / 1_000_000; // ms
        $this->assertLessThan(10, $elapsed); // Should be near-instant
    }
}
