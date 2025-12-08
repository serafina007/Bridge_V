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
    source_info = get_contract_info('source', contract_info)
    dest_info = get_contract_info('destination', contract_info)

    if not source_info or not dest_info:
        print("Error loading contract info.")
        return 0

    # 2. Establish Connections to Both Chains
    w3_source = connect_to('source')
    w3_dest = connect_to('destination')

    # 3. Load the Warden's Private Key
    # We assume the key is stored in 'secret_key.txt' as per Bridge I
    try:
        with open("secret_key.txt", "r") as f:
            private_key = f.read().strip()
        warden_account = Account.from_key(private_key)
        warden_address = warden_account.address
        print(f"Warden Address: {warden_address}")
    except Exception as e:
        print(f"Could not load private key: {e}")
        return 0

    # 4. Define Logic based on the chain being scanned
    
    # --- SCENARIO A: Scanning Source (Avalanche) for Deposits ---
    if chain == 'source':
        print("Scanning Source Chain (Avalanche) for Deposit events...")
        
        # Initialize Contracts
        source_contract = w3_source.eth.contract(address=source_info['address'], abi=source_info['abi'])
        dest_contract = w3_dest.eth.contract(address=dest_info['address'], abi=dest_info['abi'])

        # Define Block Range (Last 5 blocks)
        try:
            current_block = w3_source.eth.get_block_number()
            start_block = current_block - 5
            
            # Filter for Deposit events
            event_filter = source_contract.events.Deposit.create_filter(from_block=start_block, to_block=current_block)
            events = event_filter.get_all_entries()
            
            # Get initial nonce for the Destination chain (where we will write)
            nonce = w3_dest.eth.get_transaction_count(warden_address)

            for event in events:
                args = event['args']
                token = args['token']
                recipient = args['recipient']
                amount = args['amount']
                
                print(f"Event found: Deposit {amount} of {token} for {recipient}")

                # Action: Call wrap() on Destination
                # Function signature: wrap(address _underlying_token, address _recipient, uint256 _amount)
                tx = dest_contract.functions.wrap(token, recipient, amount).build_transaction({
                    'chainId': 97, # BSC Testnet Chain ID
                    'gas': 2000000,
                    'gasPrice': w3_dest.eth.gas_price,
                    'nonce': nonce
                })

                # Sign and Send
                signed_tx = w3_dest.eth.account.sign_transaction(tx, private_key)
                tx_hash = w3_dest.eth.send_raw_transaction(signed_tx.rawTransaction)
                print(f"Sent Wrap transaction to BSC: {tx_hash.hex()}")
                
                # Increment nonce for next transaction in loop
                nonce += 1

        except Exception as e:
            print(f"Error scanning source or sending wrap: {e}")


    # --- SCENARIO B: Scanning Destination (BSC) for Unwraps ---
    elif chain == 'destination':
        print("Scanning Destination Chain (BSC) for Unwrap events...")
        
        # Initialize Contracts
        dest_contract = w3_dest.eth.contract(address=dest_info['address'], abi=dest_info['abi'])
        source_contract = w3_source.eth.contract(address=source_info['address'], abi=source_info['abi'])

        # Define Block Range (Last 5 blocks)
        try:
            current_block = w3_dest.eth.get_block_number()
            start_block = current_block - 5
            
            # Filter for Unwrap events
            event_filter = dest_contract.events.Unwrap.create_filter(from_block=start_block, to_block=current_block)
            events = event_filter.get_all_entries()
            
            # Get initial nonce for the Source chain (where we will write)
            nonce = w3_source.eth.get_transaction_count(warden_address)

            for event in events:
                args = event['args']
                # Event signature: Unwrap(address indexed underlying_token, address indexed wrapped_token, address frm, address indexed to, uint256 amount)
                underlying_token = args['underlying_token']
                recipient = args['to']
                amount = args['amount']
                
                print(f"Event found: Unwrap {amount} of {underlying_token} for {recipient}")

                # Action: Call withdraw() on Source
                # Function signature: withdraw(address _token, address _recipient, uint256 _amount)
                tx = source_contract.functions.withdraw(underlying_token, recipient, amount).build_transaction({
                    'chainId': 43113, # Avalanche Fuji Testnet Chain ID
                    'gas': 2000000,
                    'gasPrice': w3_source.eth.gas_price,
                    'nonce': nonce
                })

                # Sign and Send
                signed_tx = w3_source.eth.account.sign_transaction(tx, private_key)
                tx_hash = w3_source.eth.send_raw_transaction(signed_tx.rawTransaction)
                print(f"Sent Withdraw transaction to Avalanche: {tx_hash.hex()}")
                
                # Increment nonce for next transaction in loop
                nonce += 1

        except Exception as e:
            print(f"Error scanning destination or sending withdraw: {e}")
