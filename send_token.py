from web3 import Web3
from config import BOT_PRIVATE_KEY, BOT_WALLET, BSC_RPC
from web3.middleware import geth_poa_middleware

ERC20_ABI = [{
    "name": "transfer",
    "type": "function",
    "inputs": [
        {"name": "_to", "type": "address"},
        {"name": "_value", "type": "uint256"}
    ],
    "outputs": [{"name": "", "type": "bool"}]
}]

def send_token(token_address, to, amount, decimals, rpc=None):
    rpc_used = rpc if rpc else BSC_RPC

    # ✅ FIX UTAMA (TANPA UBAH SISTEM)
    w3_local = Web3(Web3.HTTPProvider(rpc_used))
    w3_local.middleware_onion.inject(geth_poa_middleware, layer=0)

    nonce = w3_local.eth.get_transaction_count(BOT_WALLET)
    chain_id = w3_local.eth.chain_id

    latest_block = w3_local.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")

    if base_fee:
        max_priority = w3_local.to_wei(2, "gwei")
        max_fee = base_fee + max_priority
        gas_params = {
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": max_priority,
        }
    else:
        gas_params = {
            "gasPrice": w3_local.eth.gas_price
        }

    if token_address is None:
        tx = {
            "type": 2,
            "from": BOT_WALLET,
            "to": Web3.to_checksum_address(to),
            "value": w3_local.to_wei(amount, "ether"),
            "nonce": nonce,
            "gas": 60000,
            "chainId": chain_id,
            **gas_params
        }
    else:
        contract = w3_local.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )
        tx = contract.functions.transfer(
            Web3.to_checksum_address(to),
            int(amount * (10 ** decimals))
        ).build_transaction({
            "type": 2,
            "from": BOT_WALLET,
            "nonce": nonce,
            "gas": 120000,
            "chainId": chain_id,
            **gas_params
        })

    signed = w3_local.eth.account.sign_transaction(tx, BOT_PRIVATE_KEY)
    tx_hash = w3_local.eth.send_raw_transaction(signed.raw_transaction)
    return w3_local.to_hex(tx_hash)
