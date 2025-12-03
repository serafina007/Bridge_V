from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]



def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    #YOUR CODE HERE
    w3 = connect_to(chain)
    
    # Load contract info
    info = get_contract_info(chain, contract_info)
    contract_address = info["address"]
    abi = info["abi"]
    
    # Create contract instance
    contract = w3.eth.contract(address=contract_address, abi=abi)
    
    # Get the last block and scan the last 5 blocks
    latest_block = w3.eth.get_block_number()
    start_block = max(0, latest_block - 5)
    end_block = latest_block
    
    if chain == "source":
        event_name = "Deposit"
    else:
        event_name = "Unwrap"

    # Create event filter
    event_filter = getattr(contract.events, event_name).create_filter(from_block=start_block, to_block=end_block)
    
    events = event_filter.get_all_entries()
    if not events:
        print(f"No {event_name} events found on {chain} chain from block {start_block} to {end_block}")
        return
    
    # Load warden signing key and target chain info
    warden_sk = int(info["warden_sk"], 16)
    account = w3.eth.account.from_key(warden_sk)
    w3.eth.default_account = account.address
    
    # Load the other chain's contract info
    target_chain = "destination" if chain == "source" else "source"
    target_info = get_contract_info(target_chain, contract_info)
    target_contract = w3.eth.contract(address=target_info["address"], abi=target_info["abi"])

    # Process events
    for e in events:
        if chain == "source":
            # Call wrap on destination contract
            token = e["args"]["token"]
            recipient = e["args"]["recipient"]
            amount = e["args"]["amount"]

            tx = target_contract.functions.wrap(token, recipient, amount).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 500_000,
                "gasPrice": w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_sk)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Wrap called on destination: {tx_hash.hex()}")

        else:
            # Call withdraw on source contract
            wtoken = e["args"]["wrappedToken"] if "wrappedToken" in e["args"] else e["args"]["wrapped_token"]
            frm = e["args"]["frm"] if "frm" in e["args"] else e["args"]["from"]
            to = e["args"]["to"]
            amount = e["args"]["amount"]

            tx = target_contract.functions.withdraw(wtoken, to, amount).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 500_000,
                "gasPrice": w3.eth.gas_price
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_sk)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Withdraw called on source: {tx_hash.hex()}")

