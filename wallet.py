from web3 import Web3
from config import BOT_PRIVATE_KEY, BOT_WALLET, RPC_BY_NETWORK, BSC_RPC
from web3.middleware import geth_poa_middleware

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "_owner", "type": "address"}],
        "outputs": [{"name": "balance", "type": "uint256"}]
    },
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "outputs": [{"name": "", "type": "bool"}]
    }
]

# =========================
# RPC RESOLVER (AMAN)
# =========================
def get_w3(network=None, rpc=None):
    if rpc:
        w3 = Web3(Web3.HTTPProvider(rpc))
    elif network and network in RPC_BY_NETWORK:
        w3 = Web3(Web3.HTTPProvider(RPC_BY_NETWORK[network]))
    else:
        w3 = Web3(Web3.HTTPProvider(BSC_RPC))

    # ✅ FIX UNTUK BSC / POA CHAIN
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    return w3

# =========================
# SEND TOKEN / NATIVE
# =========================
def send_token(
    token_address,
    to,
    amount,
    decimals,
    network=None,
    rpc=None
):
    w3 = get_w3(network, rpc)

    nonce = w3.eth.get_transaction_count(BOT_WALLET)
    chain_id = w3.eth.chain_id

    # =========================
    # GAS STRATEGY AUTO
    # =========================
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")

    if base_fee:
        max_priority = w3.to_wei(2, "gwei")
        max_fee = base_fee + max_priority
        gas_params = {
            "type": 2,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": max_priority
        }
    else:
        gas_params = {
            "gasPrice": w3.eth.gas_price
        }

    # =========================
    # NATIVE COIN
    # =========================
    if token_address is None:
        tx = {
            "from": BOT_WALLET,
            "to": Web3.to_checksum_address(to),
            "value": w3.to_wei(amount, "ether"),
            "nonce": nonce,
            "gas": 60000,
            "chainId": chain_id,
            **gas_params
        }

    # =========================
    # ERC20
    # =========================
    else:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI
        )
        tx = contract.functions.transfer(
            Web3.to_checksum_address(to),
            int(amount * (10 ** decimals))
        ).build_transaction({
            "from": BOT_WALLET,
            "nonce": nonce,
            "gas": 120000,
            "chainId": chain_id,
            **gas_params
        })

    signed = w3.eth.account.sign_transaction(tx, BOT_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.to_hex(tx_hash)


# =========================
# HOT WALLET BALANCE
# =========================
def get_hot_wallet_token_balance(
    token_address,
    decimals,
    network=None,
    rpc=None
):
    w3 = get_w3(network, rpc)

    # =========================
    # NATIVE COIN
    # =========================
    if token_address is None:
        return w3.from_wei(
            w3.eth.get_balance(BOT_WALLET),
            "ether"
        )

    # =========================
    # ERC20
    # =========================
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI
    )
    raw = contract.functions.balanceOf(
        Web3.to_checksum_address(BOT_WALLET)
    ).call()
    return raw / (10 ** decimals)
