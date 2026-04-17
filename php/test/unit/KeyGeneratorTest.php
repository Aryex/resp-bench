<?php

declare(strict_types=1);

namespace RespBench\Tests\Unit;

use PHPUnit\Framework\TestCase;
use RespBench\Engine\KeyGenerator;
use RespBench\Config\KeyspaceConfig;

class KeyGeneratorTest extends TestCase
{
    public function testSequentialGenerator(): void
    {
        $config = new KeyspaceConfig(keysCount: 3, keySizeBytes: 10, keyPrefix: 'test:');
        $gen = new KeyGenerator($config);

        $this->assertSame('test:00000', $gen->nextKey());
        $this->assertSame('test:00001', $gen->nextKey());
        $this->assertSame('test:00002', $gen->nextKey());
        // Wraps around
        $this->assertSame('test:00000', $gen->nextKey());
    }

    public function testSequentialGeneratorReset(): void
    {
        $config = new KeyspaceConfig(keysCount: 100, keySizeBytes: 10, keyPrefix: 'k:');
        $gen = new KeyGenerator($config);

        $first = $gen->nextKey();
        $gen->nextKey();
        $gen->reset();
        $this->assertSame($first, $gen->nextKey());
    }
}
