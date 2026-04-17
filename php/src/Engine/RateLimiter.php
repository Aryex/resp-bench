<?php

declare(strict_types=1);

namespace RespBench\Engine;

/**
 * Leaky bucket rate limiter that enforces a constant rate without burst.
 * Matches the Java reference implementation behavior.
 */
class RateLimiter
{
    private int $intervalNanos;
    private int $nextAllowedNanos;

    private function __construct(private readonly int $ratePerSecond)
    {
        $this->intervalNanos = (int) (1_000_000_000 / $ratePerSecond);
        $this->nextAllowedNanos = hrtime(true);
    }

    public static function create(int $ratePerSecond): ?self
    {
        return $ratePerSecond > 0 ? new self($ratePerSecond) : null;
    }

    public function acquire(): void
    {
        while (true) {
            $now = hrtime(true);
            if ($now >= $this->nextAllowedNanos) {
                $this->nextAllowedNanos += $this->intervalNanos;
                return;
            }
            $waitNanos = $this->nextAllowedNanos - $now;
            if ($waitNanos > 0) {
                usleep((int) ($waitNanos / 1000));
            }
        }
    }
}
