"""
Firebase Firestore initialization and management.
Provides real-time database capabilities for temporal buffering.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from google.cloud.firestore import Client, CollectionReference, DocumentReference
from google.cloud.firestore_v1.base_client import BaseClient

from config import config

logger = logging.getLogger(__name__)

class FirebaseManager:
    """
    Manages Firebase Firestore connection and provides typed access to collections.
    Implements singleton pattern to prevent multiple initializations.
    """
    _instance: Optional['FirebaseManager'] = None
    _client: Optional[Client] = None
    _app = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Firebase with error handling and validation"""
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(config.firebase.credentials_path))
                self._app = initialize_app(cred, {
                    'projectId': config.firebase.project_id
                })
                logger.info(f"Firebase initialized for project: {config.firebase.project_id}")
            
            self._client = firestore.client()
            self._test_connection()
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            self._client = None
    
    def _test_connection(self):
        """Test Firestore connection with a simple write/read"""
        try:
            test_ref = self._client.collection('_connection_test').document('ping')
            test_ref.set({'timestamp': datetime.now().isoformat()})
            test_ref.delete()
            logger.debug("Firebase connection test successful")
        except Exception as e:
            logger.error(f"Firebase connection test failed: {e}")
            raise
    
    @property
    def client(self) -> Client:
        """Get Firestore client with null check"""
        if self._client is None:
            raise ConnectionError("Firebase client not initialized")
        return self._client
    
    def get_temporal_buffer_ref(self, block_number: int) -> CollectionReference:
        """
        Get reference to temporal buffer collection for a specific block.
        
        Args:
            block_number: Ethereum block number
            
        Returns:
            CollectionReference for block-specific temporal buffer
        """
        return self.client.collection('temporal_buffer').document(str(block_number)).collection('data')
    
    def get_confidence_scores_ref(self) -> CollectionReference:
        """Get reference to confidence scores collection"""
        return self.client.collection('confidence_scores')
    
    def get_risk_envelopes_ref(self) -> CollectionReference:
        """Get reference to risk envelopes collection"""
        return self.client.collection('risk_envelopes')
    
    def get_wallet_state_ref(self) -> DocumentReference:
        """Get reference to wallet state document"""
        return self.client.collection('wallet_state').document('current')
    
    def write_to_buffer(self, block_number: int, data_type: str, data: Dict[str, Any]) -> bool:
        """
        Write data to temporal buffer with error handling.
        
        Args:
            block_number: Block number for temporal indexing
            data_type: Type of data (pending_transactions, block_data, etc.)
            data: Dictionary containing the data
            
        Returns:
            Boolean indicating success
        """
        try:
            doc_ref = self.get_temporal_buffer_ref(block_number).document(data_type)
            doc_ref.set({
                **data,
                '_timestamp': datetime.now().isoformat(),
                '_processed': False
            })
            logger.debug(f"Written to buffer: block={block_number}, type={data_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to write to buffer: {e}")
            return False
    
    async def stream_buffer_updates(self, callback, block_number: int):
        """
        Stream updates from temporal buffer for a specific block.
        
        Args:
            callback: Async function to call with update data
            block_number: Block number to monitor
        """
        buffer_ref = self.get_temporal_buffer_ref(block_number)
        
        def on_snapshot(col_snapshot, changes, read_time):
            """Handle Firestore snapshot updates"""
            for change in changes:
                if change.type.name == 'ADDED':
                    asyncio.create_task(callback(change.document.to_dict()))
        
        # Watch the collection for changes
        buffer_watch = buffer_ref.on_snapshot(on_snapshot)
        
        # Keep the stream alive
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            buffer_watch.unsubscribe()
            logger.info("Buffer stream stopped")
    
    def cleanup_old_buffers(self, blocks_to_keep: int = 100):
        """
        Clean up temporal buffers older than specified blocks.
        
        Args:
            blocks_to_keep: Number of recent blocks to keep
        """
        try:
            # Get current block from reference
            current_doc = self.client.collection('system_state').document('current_block').get()
            if current_doc.exists:
                current_block = current_doc.to_dict().get('block_number', 0)
                cutoff_block = current_block - blocks_to_keep
                
                # Delete old buffers
                old_buffers = self.client.collection('temporal_buffer').where('block_number', '<', cutoff_block).stream()
                
                deleted_count = 0
                for doc in old_buffers:
                    # Delete all subcollections
                    for coll in doc.reference.collections():
                        for subdoc in coll.stream():
                            subdoc.reference.delete()
                    
                    doc.reference.delete()
                    deleted_count += 1
                
                logger.info(f"Cleaned up {deleted_count} old temporal buffers")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old buffers: {e}")

# Global Firebase instance
firebase_manager = FirebaseManager()