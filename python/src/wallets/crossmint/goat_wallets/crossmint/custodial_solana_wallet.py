import time
from typing import Dict
import base58
from solders.instruction import Instruction
from solders.pubkey import Pubkey
from solders.message import Message
from solders.transaction import VersionedTransaction
from solders.hash import Hash
from solders.signature import Signature
from solana.rpc.api import Client as SolanaClient
from goat.classes.wallet_client_base import Balance, Signature
from goat_wallets.solana import SolanaWalletClient, SolanaTransaction
from .api_client import CrossmintWalletsAPI


def get_locator(params: Dict) -> str:
    """Get wallet locator from parameters."""
    if "address" in params:
        return params["address"]
    if "email" in params:
        return f"email:{params['email']}:solana-custodial-wallet"
    if "phone" in params:
        return f"phone:{params['phone']}:solana-custodial-wallet"
    return f"userId:{params['userId']}:solana-custodial-wallet"


class CustodialSolanaWalletClient(SolanaWalletClient):
    """Solana custodial wallet implementation using Crossmint."""
    
    def __init__(
        self,
        address: str,
        api_client: CrossmintWalletsAPI,
        connection: SolanaClient,
        options: Dict
    ):
        """Initialize custodial wallet client.
        
        Args:
            address: Wallet address
            api_client: Crossmint API client
            connection: Solana RPC connection
            options: Additional options
        """
        super().__init__(connection)
        self._address = address
        self._client = api_client
        self._locator = get_locator(options)
        self.connection = connection
    
    def get_address(self) -> str:
        """Get wallet address."""
        return self._address
    
    def sign_message(self, message: str) -> Signature:
        """Sign a message with the wallet's private key.
        
        Args:
            message: Message to sign
            
        Returns:
            Signature object containing the signature
        """
        try:
            response = self._client.sign_message_for_custodial_wallet(
                self._locator,
                message
            )
            
            while True:
                status = self._client.check_signature_status(
                    response["id"],
                    self._address
                )
                
                if status["status"] == "success":
                    if not status.get("outputSignature"):
                        raise ValueError("Signature is undefined")
                    return Signature(signature=status["outputSignature"])
                
                if status["status"] == "failed":
                    raise ValueError("Signature failed")
                
                time.sleep(3)  # Wait 3 seconds before checking again
                
        except Exception as e:
            raise ValueError(f"Failed to sign message: {e}")
    
    def send_transaction(self, transaction: SolanaTransaction) -> Dict[str, str]:
        """Send a transaction on the Solana chain.
        
        Args:
            transaction: Transaction parameters including instructions and optional lookup tables
            
        Returns:
            Dict containing the transaction hash
        """
        # Convert instructions to solders Instructions
        instructions = []
        for instruction in transaction["instructions"]:
            # Convert dictionary to solders Instruction
            instruction = Instruction(
                program_id=instruction.program_id,
                accounts=instruction.accounts,
                data=instruction.data
            )
            instructions.append(instruction)
        
        # Create legacy message
        message = Message.new_with_blockhash(
            instructions=instructions,
            payer=Pubkey.from_string(self._address),
            blockhash=Hash.from_string("11111111111111111111111111111111")  # Match TypeScript implementation
        )
        
        # Create versioned transaction with empty signature
        transaction = VersionedTransaction.populate(
            message=message,
            signatures=[Signature.new_unique()]  # Empty signature placeholder
        )
        
        # Serialize and encode transaction
        serialized = base58.b58encode(bytes(transaction)).decode()
        
        # Create and submit transaction
        response = self._client.create_transaction_for_custodial_wallet(
            self._locator,
            serialized
        )
        
        # Wait for completion
        while True:
            status = self._client.check_transaction_status(
                self._locator,
                response["id"]
            )
            
            if status["status"] == "success":
                return {
                    "hash": status.get("onChain", {}).get("txId", "")
                }
            
            if status["status"] == "failed":
                raise ValueError(
                    f"Transaction failed: {status.get('onChain', {}).get('txId')}"
                )
            
            time.sleep(3)
    
    def balance_of(self, address: str) -> Balance:
        """Get the SOL balance of an address.
        
        Args:
            address: The address to check balance for
            
        Returns:
            Balance object containing token information and value
        """
        pubkey = Pubkey.from_string(address)
        balance = self.connection.get_balance(pubkey)
        
        return Balance(
            value=str(balance.value / 10**9),
            in_base_units=str(balance.value),
            decimals=9,
            symbol="SOL",
            name="Solana"
        )

    def send_raw_transaction(self, transaction: str) -> Dict[str, str]:
        """Send a raw transaction on the Solana chain.
        
        Args:
            transaction: Base58 encoded transaction
            
        Returns:
            Dict containing the transaction hash
        """
        response = self._client.create_transaction_for_custodial_wallet(
            self._locator,
            transaction
        )
        
        while True:
            status = self._client.check_transaction_status(
                self._locator,
                response["id"]
            )
            
            if status["status"] == "success":
                return {
                    "hash": status.get("onChain", {}).get("txId", "")
                }
            
            if status["status"] == "failed":
                raise ValueError(
                    f"Transaction failed: {status.get('onChain', {}).get('txId')}"
                )
            
            time.sleep(3)


def custodial_factory(api_client: CrossmintWalletsAPI):
    """Factory function to create custodial wallet instances."""
    def create_custodial(options: dict) -> CustodialSolanaWalletClient:
        """Create a new custodial wallet instance."""
        locator = get_locator(options)
        wallet = api_client.get_wallet(locator)
        
        return CustodialSolanaWalletClient(
            wallet["address"],
            api_client,
            options["connection"],
            options
        )
    
    return create_custodial
