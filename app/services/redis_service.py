#!/usr/bin/env python3
"""Redis service for sending verification data using Redis Streams"""

import json
import hashlib
import os
from datetime import datetime
from typing import Optional
import logging
import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self):
        # Redis configuration from environment variables
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_password = os.getenv('REDIS_PASSWORD', '')
        self.redis_username = os.getenv('REDIS_USERNAME', 'default')
        self.stream_name = os.getenv('REDIS_STREAM_NAME', 'verification_stream')
        
        # Redis connection configuration
        self.redis_config = {
            'host': self.redis_host,
            'port': self.redis_port,
            'password': self.redis_password if self.redis_password else None,
            'username': self.redis_username if self.redis_username != 'default' else None,
            'decode_responses': False,  # Keep as bytes for stream compatibility
            'socket_timeout': 30,
            'socket_connect_timeout': 30,
            'retry_on_timeout': True,
            'health_check_interval': 30
        }
        
        # Redis stream configuration
        self.max_stream_length = 10000  # Keep last 10k messages
        
        # Connection status
        self.is_connected = False
        self.connection_error = None
        
        # Redis client
        self.redis_client = None
        
        # Log configuration on initialization
        logger.info(f"Redis Service initialized with:")
        logger.info(f"  Host: {self.redis_host}")
        logger.info(f"  Port: {self.redis_port}")
        logger.info(f"  Stream: {self.stream_name}")
    
    def _get_redis_client(self) -> redis.Redis:
        """Get or create Redis client with connection pooling"""
        if self.redis_client is None:
            try:
                self.redis_client = redis.Redis(**self.redis_config)
                logger.info("Redis client created successfully")
            except Exception as e:
                logger.error(f"Failed to create Redis client: {e}")
                raise
        return self.redis_client
    
    async def test_connection(self) -> bool:
        """Test Redis connection and update connection status"""
        try:
            logger.info(f"Testing Redis connection to {self.redis_config['host']}:{self.redis_config['port']}...")
            
            client = self._get_redis_client()
            
            # Test basic connectivity with ping
            result = client.ping()
            if result:
                self.is_connected = True
                self.connection_error = None
                logger.info(f"✅ Redis connection successful")
                
                # Test stream operations
                test_data = {"test": "connection", "timestamp": datetime.now().isoformat()}
                stream_id = client.xadd("test_stream", test_data, maxlen=1)
                logger.info(f"✅ Redis stream test successful, message ID: {stream_id}")
                
                # Clean up test stream
                client.delete("test_stream")
                
                return True
            else:
                self.connection_error = "Redis ping failed"
                self.is_connected = False
                logger.error(f"❌ Redis ping failed")
                return False
                
        except ConnectionError as e:
            self.connection_error = f"Redis connection error: {str(e)}"
            self.is_connected = False
            logger.error(f"❌ Redis connection failed: {self.connection_error}")
            return False
        except TimeoutError as e:
            self.connection_error = f"Redis timeout error: {str(e)}"
            self.is_connected = False
            logger.error(f"❌ Redis timeout: {self.connection_error}")
            return False
        except Exception as e:
            self.connection_error = f"Redis test error: {str(e)}"
            self.is_connected = False
            logger.error(f"❌ Redis connection test failed: {self.connection_error}")
            return False
    
    async def health_check(self) -> dict:
        """Health check for Redis service"""
        await self.test_connection()
        return {
            "service": "redis",
            "status": "healthy" if self.is_connected else "unhealthy",
            "host": self.redis_config['host'],
            "port": self.redis_config['port'],
            "stream": self.stream_name,
            "connected": self.is_connected,
            "error": self.connection_error
        }
    
    # OCR hash creation removed - evidence hash will be created in Rust enclave
    
    def _create_verification_payload(self, document_type: str, extracted_data: dict, user_corrections: dict = None) -> dict:
        """Create payload for government API verification (without @entity - handled in Rust)"""
        try:
            # Use corrected data if provided, otherwise use extracted data
            final_data = user_corrections if user_corrections else extracted_data
            
            if document_type == "pan":
                return {
                    "pan": final_data.get('pan'),
                    "name_as_per_pan": final_data.get('name'),
                    "date_of_birth": final_data.get('date_of_birth'),
                    "consent": "Y",
                    "reason": "For onboarding customers"
                }
            else:
                raise ValueError(f"Unsupported document type: {document_type}. Only 'pan' is supported.")
                
        except Exception as e:
            logger.error(f"Failed to create verification payload: {e}")
            raise
    
    async def send_verification_request(self, user_wallet: str, did_id: str, document_type: str, verification_data: dict, extracted_data: dict = None, user_corrections: dict = None) -> bool:
        """
        Send verification request to Redis Stream for enclave processing
        
        Args:
            user_wallet: User's wallet address
            did_id: DID identifier (0=PAN covers 18+/citizenship/personal_id)
            document_type: Type of document ("pan" only)
            verification_data: Final verification data to be sent to government API
            extracted_data: Original OCR extracted data (not used for hash - done in Rust)
            user_corrections: User corrections to OCR data
        """
        try:
            # Create verification payload for government API (no @entity - handled in Rust)
            document_data = self._create_verification_payload(document_type, verification_data, user_corrections)
            
            # Prepare verification request message (no ocr_hash - evidence hash created in Rust)
            verification_message = {
                "user_wallet": user_wallet,
                "did_id": str(did_id),
                "verification_type": document_type,
                "document_data": document_data,
                "timestamp": datetime.now().isoformat(),
                "status": "pending_verification"  # NOT "verified"
            }
            
            logger.info(f"Sending PAN verification request to Redis for enclave processing")
            logger.info(f"Request: {json.dumps(verification_message, indent=2)}")
            
            # Send to Redis Stream
            success = await self._send_to_redis_stream(verification_message)
            
            if success:
                logger.info("✅ PAN verification request successfully sent to Redis")
                return True
            else:
                logger.error("❌ Failed to send PAN verification request to Redis")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send verification request: {e}")
            return False
    
    async def send_verification_data(self, user_data: dict) -> bool:
        """
        DEPRECATED: Legacy method for backward compatibility
        Use send_verification_request instead
        """
        logger.warning("send_verification_data is deprecated. Use send_verification_request instead.")
        
        # Convert legacy format to new PAN format
        return await self.send_verification_request(
            user_wallet=user_data.get('wallet_address'),
            did_id=user_data.get('did', 0),
            document_type="pan",  # Changed to PAN for all verifications
            verification_data={
                'pan': user_data.get('pan', user_data.get('aadhaar_number')),  # Use PAN or fallback to aadhaar
                'name': user_data.get('full_name'),
                'date_of_birth': user_data.get('date_of_birth'),
                'phone_number': user_data.get('phone_number')
            },
            extracted_data=user_data
        )
    
    async def _send_to_redis_stream(self, verification_message: dict) -> bool:
        """Send message to Redis Stream"""
        try:
            client = self._get_redis_client()
            
            # Flatten the message for Redis stream (all values must be strings)
            flattened_message = {}
            for key, value in verification_message.items():
                if isinstance(value, dict):
                    # Convert nested dict to JSON string
                    flattened_message[key] = json.dumps(value)
                else:
                    # Convert other types to string
                    flattened_message[key] = str(value)
            
            # Add message to Redis Stream with automatic ID generation
            stream_id = client.xadd(
                self.stream_name,
                flattened_message,
                maxlen=self.max_stream_length  # Keep only last N messages
            )
            
            logger.info(f"✅ Message sent to Redis stream '{self.stream_name}' with ID: {stream_id}")
            
            # Log stream info
            stream_info = client.xinfo_stream(self.stream_name)
            logger.info(f"Stream info - Length: {stream_info.get('length', 0)}, "
                       f"First ID: {stream_info.get('first-entry', ['N/A'])[0] if stream_info.get('first-entry') else 'N/A'}, "
                       f"Last ID: {stream_info.get('last-entry', ['N/A'])[0] if stream_info.get('last-entry') else 'N/A'}")
            
            return True
            
        except RedisError as e:
            logger.error(f"Redis stream error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending to Redis stream: {e}")
            return False
    
    async def get_stream_info(self) -> dict:
        """Get information about the verification stream"""
        try:
            client = self._get_redis_client()
            
            # Check if stream exists
            if not client.exists(self.stream_name):
                return {
                    "stream_exists": False,
                    "message": f"Stream '{self.stream_name}' does not exist"
                }
            
            # Get stream information
            stream_info = client.xinfo_stream(self.stream_name)
            
            return {
                "stream_exists": True,
                "stream_name": self.stream_name,
                "length": stream_info.get('length', 0),
                "first_entry_id": stream_info.get('first-entry', ['N/A'])[0] if stream_info.get('first-entry') else 'N/A',
                "last_entry_id": stream_info.get('last-entry', ['N/A'])[0] if stream_info.get('last-entry') else 'N/A',
                "radix_tree_keys": stream_info.get('radix-tree-keys', 0),
                "radix_tree_nodes": stream_info.get('radix-tree-nodes', 0),
                "groups": stream_info.get('groups', 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get stream info: {e}")
            return {
                "stream_exists": False,
                "error": str(e)
            }
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            try:
                self.redis_client.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
            finally:
                self.redis_client = None
                self.is_connected = False

# Global instance
redis_service = RedisService()

def get_redis_service() -> RedisService:
    """Dependency injection for Redis service"""
    return redis_service
