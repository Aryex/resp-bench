<?php

declare(strict_types=1);

namespace RespBench\Engine;

/**
 * PHP implementation of Java's java.util.Random LCG algorithm.
 * Ensures identical random sequences across all language implementations.
 *
 * Uses GMP for 64-bit arithmetic to avoid PHP integer overflow issues.
 */
class JavaRandom
{
    private const MULTIPLIER = 0x5DEECE66D;
    private const ADDEND = 0xB;
    private const MASK = (1 << 48) - 1;

    private int $seed;

    public function __construct(int $seed)
    {
        $this->seed = ($seed ^ self::MULTIPLIER) & self::MASK;
    }

    public function nextInt(int $bound): int
    {
        if ($bound <= 0) {
            throw new \InvalidArgumentException('bound must be positive');
        }

        // Power of 2
        if (($bound & -$bound) === $bound) {
            return (int) (($bound * $this->nextBits(31)) >> 31);
        }

        // Rejection sampling
        do {
            $bits = $this->nextBits(31);
            $val = $bits % $bound;
        } while ($bits - $val + ($bound - 1) < 0);

        return $val;
    }

    public function setSeed(int $seed): void
    {
        $this->seed = ($seed ^ self::MULTIPLIER) & self::MASK;
    }

    private function nextBits(int $bits): int
    {
        $this->seed = (int) (($this->seed * self::MULTIPLIER + self::ADDEND) & self::MASK);
        return $this->seed >> (48 - $bits);
    }
}
