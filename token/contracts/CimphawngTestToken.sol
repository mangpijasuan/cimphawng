// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @notice Experimental test token. No mainnet deployment or paper-wallet conversion.
contract CimphawngTestToken is ERC20 {
    error TestnetOnly(uint256 chainId);

    // Provisional testing supply; not a mainnet tokenomics commitment.
    uint256 public constant INITIAL_SUPPLY = 1_000_000 * 10 ** 18;

    constructor(address recipient) ERC20("Cimphawng Test Token", "CIMP") {
        if (block.chainid != 84532 && block.chainid != 31337 && block.chainid != 1337) {
            revert TestnetOnly(block.chainid);
        }
        _mint(recipient, INITIAL_SUPPLY);
    }
}
