<?php

declare(strict_types=1);

namespace RespBench\Engine;

use RespBench\Config\CommandConfig;

/**
 * Selects commands based on weighted random distribution.
 */
class CommandSelector
{
    /** @var float[] cumulative weights */
    private array $cumulativeWeights;
    /** @var CommandConfig[] */
    private array $commands;

    /**
     * @param CommandConfig[] $commands
     */
    public function __construct(array $commands)
    {
        $this->commands = $commands;
        $this->cumulativeWeights = [];
        $cumulative = 0.0;
        foreach ($commands as $cmd) {
            $cumulative += $cmd->weight;
            $this->cumulativeWeights[] = $cumulative;
        }
    }

    public function select(): CommandConfig
    {
        $r = mt_rand() / mt_getrandmax() * end($this->cumulativeWeights);
        foreach ($this->cumulativeWeights as $i => $w) {
            if ($r <= $w) {
                return $this->commands[$i];
            }
        }
        return end($this->commands);
    }
}
