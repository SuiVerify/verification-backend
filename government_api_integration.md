# SuiVerify Government API Integration Tasks

## Overview
Python backend sends verification payloads to Rust enclave via Redis. **All government API calls happen only in Rust enclave.**

## Current Problem
- Python backend sets `is_verified=1` after OCR + Face + OTP
- Redis streams receive `"result": "verified"` without actual verification
- Evidence hash only contains Aadhaar data, not verification payload

## New Architecture Flow
1. Python: OCR extraction → User correction → Send payload to Redis
2. Rust Enclave: Consume Redis → Government API verification → Evidence hash → Signing

## DID Type Mappings
- **DID Type 0 (PAN Card)**: Covers all verification use cases
  - **18+ Age Verification**: PAN card verifies date of birth for age confirmation
  - **Citizenship Verification**: PAN card confirms Indian citizenship status
  - **Personal Identity Verification**: PAN card provides government-issued identity proof
  - **Financial Identity**: PAN card enables financial transactions and KYC compliance

**Note**: All verification flows now use PAN card as the primary document type. The `did_id=0` covers comprehensive identity verification including age, citizenship, and personal identification through a single PAN verification process.

---

## Task 1: Authentication Token Management (RUST ENCLAVE ONLY)
**File**: Rust enclave codebase

### Sandbox API Authentication Details:

#### Authentication Request:
```bash
curl --request POST \
     --url https://api.sandbox.co.in/authenticate \
     --header 'accept: application/json' \
     --header 'x-api-key: key_test_97ac73c9c6ce4778b7277dfba91b51ac' \
     --header 'x-api-secret: secret_test_888e16839c154715a6f0c20b2b6f3a2c'
```

#### Authentication Response:
```json
{
  "code": 200,
  "timestamp": 1760865108385,
  "access_token": "eyJ0eXAiOiJKV1MiLCJhbGciOiJSU0FTU0FfUFNTX1NIQV81MTIiLCJraWQiOiIwYzYwMGUzMS01MDAwLTRkYTItYjM3YS01ODdkYTA0ZTk4NTEifQ.eyJyZWZyZXNoX3Rva2VuIjoiZXlKMGVYQWlPaUpLVjFNaUxDSmhiR2NpT2lKU1UwRlRVMEZmVUZOVFgxTklRVjgxTVRJaUxDSnJhV1FpT2lJd1l6WXdNR1V6TVMwMU1EQXdMVFJrWVRJdFlqTTNZUzAxT0Rka1lUQTBaVGs4TlRFaWZRLmV5SnpkV0lpT2lKclpYbGZkR1Z6ZEY4NU4yRmpOek5qT1dNMlkyVTBOemM0WWpjeU56ZGtabUpoT1RGaU5URmhZeUlzSW1Gd2FWOXJaWGtpT2lKclpYbGZkR1Z6ZEY4NU4yRmpOek5qT1dNMlkyVTBOemM0WWpjeU56ZGtabUpoT1RGaU5URmhZeUlzSW5kdmNtdHpjR0ZqWlY5cFpDSTZJams0WWpWaFptWmhMV1JrTVdNdE5EUXhaUzFoTmpRd0xUQXpObUpsWmpneVlUQmxOQ0lzSW1GMVpDSTZJa0ZRU1NJc0ltbHVkR1Z1ZENJNklsSkZSbEpGVTBoZlZFOUxSVTRpTENKcGMzTWlPaUp3Y205a01TMWhjR2t1YzJGdVpHSnZlQzVqYnk1cGJpSXNJbVY0Y0NJNk1UYzVNalF3TVRFd09Dd2lhV0YwSWpveE56WXdPRFkxTVRBNGZRLkdFU1B0UV9HT1hiRElsdTRfQWE4alQzamtWUE9BQzhfcnN3NldtYUVRUnV6UUQ3MWJzOXN0d1dtOU0zOC1uT19zNGMyMjR0QmdITmZvU1NRclgwZDhkbHNmaHg5ekZYZUExbGEyRVdZMkdBQnlBc3pYX1ZHX1pOVmF6eV9TWWV6ODY1ZVI2S3N3bzQzeW5oano1V0Rza2FhRWI1TzBEOVgtRDcwR0pnbTNoUnlObUVMcVNab2FGNDdsLWU1UmR4Z1JsQzhrYlhWT19UcHNWTVoyVlFVTGptY0pPTW0yX3VFdGo1TzRsTmdDVXpscHV4MzJNUWp2MzRiaGZTRnlFRU8yZEJ0YnBjVDBiX0g5LW1Bb01nd1J2OFBISW1QY0ZkemdKWksyTkMwTnhqUDBDalhVQUw2VklXR3JGLVpMNExEYzloX0xVNDRVMVh0bm0xcFZyUWVTUSIsIndvcmtzcGFjZV9pZCI6Ijk4YjVhZmZhLWRkMWMtNDQxZS1hNjQwLTAzNmJlZjgyYTBlNCIsInN1YiI6ImtleV90ZXN0Xzk3YWM3M2M5YzZjZTQ3NzhiNzI3N2RmYmE5MWI1MWFjIiwiYXBpX2tleSI6ImtleV90ZXN0Xzk3YWM3M2M5YzZjZTQ3NzhiNzI3N2RmYmE5MWI1MWFjIiwiYXVkIjoiQVBJIiwiaW50ZW50IjoiQUNDRVNTX1RPS0VOIiwiaXNzIjoicHJvZDEtYXBpLnNhbmRib3guY28uaW4iLCJpYXQiOjE3NjA4NjUxMDgsImV4cCI6MTc2MDk1MTUwOH0.Zy74ueaL6XRYdK8PwoZBnmru8Vvn0-R515S1-lJxqauHHI9DShhJCpjuQX0Xib5c6O6yjzalBdA8on3mSQcu8n9BneOSVT4VgI-yk7w3_eVS60QEBI5HqGlMzMp4RXMTCUxZsK44OLVF70a-NRL6nu3qUGIfu7UbfUejPfBCB9TQtwsO5wKyTnIBeLUM5ClSbrnbC3dSpVBmCEgnEKOprn72Gth7QEclDmVMaMNNnpYJbvVc7QRipQG7jHHGcIofw6Ia3a5SEfa1d-Zr-f2bDjPGIEFZ3n-lYb1bAq58nJhP7ZGny030BTOd1BVitq0RCb0bLBnPgJZZCqZBPGq_rg",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1MiLCJhbGciOiJSU0FTU0FfUFNTX1NIQV81MTIiLCJraWQiOiIwYzYwMGUzMS01MDAwLTRkYTItYjM3YS01ODdkYTA0ZTk4NTEifQ.eyJ3b3Jrc3BhY2VfaWQiOiI5OGI1YWZmYS1kZDFjLTQ0MWUtYTY0MC0wMzZiZWY4MmEwZTQiLCJzdWIiOiJrZXlfdGVzdF85N2FjNzNjOWM2Y2U0Nzc4YjcyNzdkZmJhOTFiNTFhYyIsImFwaV9rZXkiOiJrZXlfdGVzdF85N2FjNzNjOWM2Y2U0Nzc4YjcyNzdkZmJhOTFiNTFhYyIsImF1ZCI6IkFQSSIsImludGVudCI6IkFDQ0VTU19UT0tFTiIsImlzcyI6InByb2QxLWFwaS5zYW5kYm94LmNvLmluIiwiaWF0IjoxNzYwODY1MTA4LCJleHAiOjE3NjA5NTE1MDh9.YD-i1DAaVIIhcPXIsdVCWUvea1pWoXOsLTE9M9lFSC5Z7hWtyI48LbK1W-Z9HzJkLLJkObsNezRVRMXK6JxOUiaUSrnaghLbWWPl0vZ00cTUMJ3o4Kj1VeB62oDgQ4sRO6Ob0bPt7hvA1JCSyDjGTrGwzZcA5WnrhJSI_uiDTCGkWe0Q6BeuNKmPqKq-nd4UJATydZlg7iQXV8kwaXvYAYbL6wWY_BvncUwXMGROxoZTa6TF8Wz4Hv1Uptk_o5yx1RZXSoB2xZLTX1wYXNLpeYM2xeq1yXAR_r4pX7FiJS5E4-t9xBFNNJCsWyWCYSqBzWOI6cdHjt14d-o06OEM6Q"
  },
  "transaction_id": "d67676fe-3d29-4b9d-992c-c35f149a848e"
}
```

### Requirements:
- Store Sandbox API credentials in enclave
- Implement JWT token refresh every 24 hours in Rust
- Handle token expiration gracefully
- Parse JWT expiration from token payload

### Rust Implementation:
```rust
use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Deserialize)]
pub struct AuthResponse {
    pub code: u16,
    pub timestamp: u64,
    pub access_token: String,
    pub data: AuthData,
    pub transaction_id: String,
}

#[derive(Debug, Deserialize)]
pub struct AuthData {
    pub access_token: String,
}

pub struct SandboxAuthService {
    api_key: String,
    api_secret: String,
    base_url: String,
    access_token: Option<String>,
    token_expiry: Option<SystemTime>,
}

impl SandboxAuthService {
    pub fn new() -> Self {
        Self {
            api_key: "key_test_97ac73c9c6ce4778b7277dfba91b51ac".to_string(),
            api_secret: "secret_test_888e16839c154715a6f0c20b2b6f3a2c".to_string(),
            base_url: "https://api.sandbox.co.in".to_string(),
            access_token: None,
            token_expiry: None,
        }
    }
    
    pub async fn get_valid_token(&mut self) -> Result<String, Box<dyn std::error::Error>> {
        // Check if current token is valid and not expired
        if let (Some(token), Some(expiry)) = (&self.access_token, &self.token_expiry) {
            if SystemTime::now() < *expiry {
                return Ok(token.clone());
            }
        }
        
        // Token expired or missing, refresh it
        self.refresh_token().await?;
        Ok(self.access_token.as_ref().unwrap().clone())
    }
    
    pub async fn refresh_token(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        let client = reqwest::Client::new();
        
        let response = client
            .post(&format!("{}/authenticate", self.base_url))
            .header("accept", "application/json")
            .header("x-api-key", &self.api_key)
            .header("x-api-secret", &self.api_secret)
            .send()
            .await?;
            
        let auth_response: AuthResponse = response.json().await?;
        
        if auth_response.code == 200 {
            self.access_token = Some(auth_response.data.access_token);
            
            // JWT expires in 24 hours, set expiry to 23 hours for safety
            self.token_expiry = Some(
                SystemTime::now() + std::time::Duration::from_secs(23 * 60 * 60)
            );
        }
        
        Ok(())
    }
}
```

---

## Task 2: Government Verification Service (RUST ENCLAVE ONLY)
**File**: Rust enclave codebase

### Requirements:
- Call Sandbox API for PAN verification from enclave
- Handle different document types (PAN, Aadhaar, etc.)
- Return structured verification response

### Rust Implementation:
```rust
pub struct GovernmentVerificationService {
    auth_service: SandboxAuthService,
}

impl GovernmentVerificationService {
    async fn verify_pan(&mut self, pan: &str, name: &str, dob: &str) -> Result<VerificationResponse, Error> {
        let token = self.auth_service.get_valid_token().await?;
        
        let payload = json!({
            "@entity": "in.co.sandbox.kyc.pan_verification.request",
            "pan": pan,
            "name_as_per_pan": name,
            "date_of_birth": dob,
            "consent": "Y",
            "reason": "For onboarding customers"
        });
        
        // Make API call to sandbox from within enclave
        // Return verification response
    }
}
```

---

## Task 3: Update Redis Stream Payload Structure (PYTHON)
**File**: `app/services/redis_service.py`

### Changes Required:
1. **Remove premature verification status**
2. **Send verification request payload for enclave consumption**
3. **No API calls in Python**

### New Redis Message Format:
```python
verification_message = {
    "user_wallet": user_wallet,
    "did_id": "0",  # PAN covers all verification types (18+, citizenship, personal_id)
    "verification_type": "pan",  # Only PAN supported
    "document_data": {
        "pan": extracted_pan,
        "name_as_per_pan": corrected_name,
        "date_of_birth": corrected_dob,
        "consent": "Y",
        "reason": "For onboarding customers"
        # Note: @entity field removed - handled in Rust enclave
    },
    # Note: ocr_hash removed - evidence hash created in Rust enclave
    "timestamp": current_timestamp,
    "status": "pending_verification"  # Not "verified"
}
```

### Updated Methods:
```python
def send_verification_request(self, user_wallet: str, did_id: str, document_type: str, verification_data: dict):
    # Send verification request to Redis stream
    # Rust enclave will consume and verify
    # NO API calls here
    pass
```

---

## Task 4: Update KYC Router Logic (PYTHON)
**File**: `app/routers/kyc.py`

### Changes Required:
1. **Remove `is_verified=1` setting**
2. **Add data correction endpoint**
3. **Send verification request to Redis only**

### New Endpoints:
```python
@router.post("/api/kyc/request-correction")
async def request_data_correction(correction_data: dict):
    # Allow user to correct OCR extracted data
    # Return corrected data for confirmation
    # NO API calls here
    pass

@router.post("/api/kyc/confirm-and-verify")  
async def confirm_and_verify(user_wallet: str, did_id: str, final_data: dict):
    # User confirms corrected data
    # Send to Redis stream for enclave verification
    # Do NOT set is_verified=1
    # Do NOT call government APIs
    
    # Send to Redis for enclave verification
    await redis_service.send_verification_request(
        user_wallet=user_wallet,
        did_id=did_id, 
        document_type="pan",
        verification_data=final_data
    )
    
    return {"status": "verification_requested", "message": "Verification in progress"}
```

---

## Task 5: Update OTP Router (PYTHON)
**File**: `app/routers/otp.py`

### Changes Required:
1. **Remove `is_verified=1` setting**  
2. **Send verification request to Redis only**

### Updated Logic:
```python
# After OTP verification success
# Do NOT set: user_data.is_verified = 1
# Do NOT call government APIs

# Send verification request to enclave via Redis
redis_data = {
    "user_wallet": user_wallet,
    "did_id": did_id,
    "verification_type": "pan",
    "document_data": extracted_and_corrected_data,
    "status": "pending_verification"
}

await redis_service.send_verification_request(redis_data)
```

---

## Task 6: Remove Government API Code from Python
**Files**: All Python files

### Changes Required:
1. **Remove any government API service from Python**
2. **Remove authentication token management from Python**
3. **Python only handles: OCR, Face detection, OTP, Redis messaging**

---

## Task 7: Rust Enclave - Complete Verification System
**File**: Rust enclave codebase

### Requirements:
1. **Consume Redis verification requests**
2. **Manage authentication tokens**
3. **Call government APIs within enclave**
4. **Generate evidence hash from complete verification**
5. **Sign verification result in enclave**

### Rust Implementation Structure:
```rust
pub struct VerificationProcessor {
    redis_client: RedisClient,
    gov_service: GovernmentVerificationService,
}

impl VerificationProcessor {
    async fn start_processing(&mut self) {
        loop {
            // Consume from Redis stream
            let requests = self.redis_client.consume_verification_requests().await;
            
            for request in requests {
                let result = self.process_verification(request).await;
                self.send_result_back(result).await;
            }
        }
    }
    
    async fn process_verification(&mut self, request: VerificationRequest) -> VerificationResult {
        // 1. Call government API within enclave
        let gov_response = self.gov_service.verify_pan(
            &request.document_data.pan,
            &request.document_data.name,
            &request.document_data.dob
        ).await?;
        
        // 2. Generate evidence hash from request + response
        let evidence_hash = self.create_evidence_hash(&request, &gov_response);
        
        // 3. Sign the evidence hash in enclave
        let signature = self.sign_evidence(evidence_hash.clone());
        
        // 4. Return complete verification result
        VerificationResult {
            user_wallet: request.user_wallet,
            did_id: request.did_id,
            verification_success: gov_response.success,
            evidence_hash,
            enclave_signature: signature,
            gov_api_response: gov_response,
            verified_at: Utc::now().to_rfc3339(),
        }
    }
}
```

---

## Task 8: Evidence Hash Generation (RUST ENCLAVE)
**File**: Rust enclave codebase

### Government API Response Structure:
```json
{
  "code": 200,
  "timestamp": 1760865505809,
  "data": {
    "@entity": "in.co.sandbox.kyc.pan_verification.response",
    "pan": "HJTPB9891M",
    "status": "valid",
    "remarks": null,
    "name_as_per_pan_match": true,
    "date_of_birth_match": true,
    "category": "individual",
    "aadhaar_seeding_status": "y"
  },
  "transaction_id": "2bfc9f4c-e3c9-43d0-aef6-27c9082d7ce0"
}
```

### Evidence Hash Input (Stable Fields + Actual Data):
**For reproducible hash generation, include both verification results and actual verified data:**
```json
{
  "pan": "HJTPB9891M",
  "status": "valid",
  "name_as_per_pan": "Ashwin Balaguru",
  "date_of_birth": "27/10/2004", 
  "name_as_per_pan_match": true,
  "date_of_birth_match": true,
  "category": "individual",
  "aadhaar_seeding_status": "y"
}
```

**Benefits of including actual data:**
- Stronger evidence integrity (can verify what specific data was verified)
- More comprehensive audit trail
- Allows reconstruction of verification context
- Better compliance documentation

### Rust Implementation:
```rust
use serde_json::{json, Value};
use sha2::{Sha256, Digest};

#[derive(Debug, Deserialize)]
pub struct PanVerificationData {
    pub pan: String,
    pub status: String,
    pub name_as_per_pan: Option<String>,
    pub date_of_birth: Option<String>,
    pub name_as_per_pan_match: bool,
    pub date_of_birth_match: bool,
    pub category: String,
    pub aadhaar_seeding_status: String,
}

impl VerificationProcessor {
    fn create_evidence_hash(&self, gov_response: &GovernmentResponse, user_data: &UserSubmissionData) -> String {
        // Include both API response and user-submitted data for complete evidence
        let stable_data = json!({
            "pan": gov_response.data.pan,
            "status": gov_response.data.status,
            "name_as_per_pan": user_data.name, // Actual name submitted by user
            "date_of_birth": user_data.date_of_birth, // Actual DOB submitted by user
            "name_as_per_pan_match": gov_response.data.name_as_per_pan_match,
            "date_of_birth_match": gov_response.data.date_of_birth_match,
            "category": gov_response.data.category,
            "aadhaar_seeding_status": gov_response.data.aadhaar_seeding_status
        });
        
        // Create deterministic hash with sorted keys
        let mut sorted_keys: Vec<_> = stable_data.as_object().unwrap().keys().collect();
        sorted_keys.sort();
        
        let ordered_data = sorted_keys.iter()
            .map(|key| format!("{}:{}", key, stable_data[*key]))
            .collect::<Vec<_>>()
            .join("|");
        
        // Generate SHA256 hash
        let mut hasher = Sha256::new();
        hasher.update(ordered_data.as_bytes());
        format!("{:x}", hasher.finalize())
    }
}
    
    fn create_evidence_with_request(&self, request: &VerificationRequest, gov_response: &GovernmentResponse) -> EvidencePackage {
        let evidence_hash = self.create_evidence_hash(gov_response);
        
        EvidencePackage {
            verification_request: request.clone(),
            government_response: gov_response.clone(),
            evidence_hash: evidence_hash.clone(),
            enclave_signature: self.sign_evidence(&evidence_hash),
            verified_at: Utc::now().to_rfc3339(),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct EvidencePackage {
    pub verification_request: VerificationRequest,
    pub government_response: GovernmentResponse,
    pub evidence_hash: String,
    pub enclave_signature: String,
    pub verified_at: String,
}
```

### Hash Reproducibility Test:
```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_evidence_hash_reproducibility() {
        let response1 = create_mock_response("transaction_id_1", 1760865505809);
        let response2 = create_mock_response("transaction_id_2", 1760865999999);
        
        let hash1 = processor.create_evidence_hash(&response1);
        let hash2 = processor.create_evidence_hash(&response2);
        
        // Hashes should be identical despite different timestamps/transaction_ids
        assert_eq!(hash1, hash2);
    }
}
```

---

## Task 3: Update Redis Stream Payload Structure
**File**: `app/services/redis_service.py`

### Changes Required:
1. **Remove premature verification status**
2. **Send verification request payload instead of result**
3. **Update message structure**

### New Redis Message Format:
```python
verification_message = {
    "user_wallet": user_wallet,
    "did_id": "0",  # PAN covers all verification types (18+, citizenship, personal_id)
    "verification_type": "pan",  # Only PAN supported
    "document_data": {
        "pan": extracted_pan,
        "name_as_per_pan": corrected_name,
        "date_of_birth": corrected_dob,
        "consent": "Y",
        "reason": "For onboarding customers"
        # Note: @entity field removed - handled in Rust enclave
    },
    # Note: ocr_hash removed - evidence hash created in Rust enclave
    "timestamp": current_timestamp,
    "status": "pending_verification"  # Not "verified"
}
```

### Updated Methods:
```python
def _create_verification_payload(self, document_type: str, extracted_data: dict, user_corrections: dict) -> dict:
    # Create payload for government API verification
    # Include user corrections if provided
    pass

def send_verification_request(self, user_wallet: str, did_id: str, document_type: str, verification_data: dict):
    # Send verification request to Redis stream
    # Rust enclave will consume and verify
    pass
```

---

## Task 4: Update KYC Router Logic
**File**: `app/routers/kyc.py`

### Changes Required:
1. **Remove `is_verified=1` setting**
2. **Add data correction endpoint**
3. **Send verification request to Redis**

### New Endpoints:
```python
@router.post("/api/kyc/request-correction")
async def request_data_correction(correction_data: dict):
    # Allow user to correct OCR extracted data
    # Return corrected data for confirmation
    pass

@router.post("/api/kyc/confirm-and-verify")  
async def confirm_and_verify(user_wallet: str, did_id: str, final_data: dict):
    # User confirms corrected data
    # Send to Redis stream for actual verification
    # Do NOT set is_verified=1
    
    # Send to Redis for enclave verification
    await redis_service.send_verification_request(
        user_wallet=user_wallet,
        did_id=did_id, 
        document_type="pan",
        verification_data=final_data
    )
    
    return {"status": "verification_requested", "message": "Verification in progress"}
```

---

## Task 5: Update OTP Router
**File**: `app/routers/otp.py`

### Changes Required:
1. **Remove `is_verified=1` setting**  
2. **Change Redis message to verification request**

### Updated Logic:
```python
# After OTP verification success
# Do NOT set: user_data.is_verified = 1

# Instead send PAN verification request
redis_data = {
    "user_wallet": user_wallet,
    "did_id": "0",  # PAN covers all verification types
    "verification_type": "pan",  # Only PAN supported
    "document_data": extracted_and_corrected_data,
    "status": "pending_verification"
}

await redis_service.send_verification_request(redis_data)
```

---

## Task 6: Evidence Hash Updates
**File**: `app/services/redis_service.py` and `app/services/kafka_service.py`

### Changes Required:
1. **Hash the complete verification payload**
2. **Include government API response in hash**

### New Evidence Hash Logic:
```python
def _create_evidence_hash(self, verification_payload: dict, gov_response: dict) -> str:
    # Combine verification request + government response
    combined_data = {
        "request": verification_payload,
        "response": gov_response,
        "verified_at": datetime.utcnow().isoformat()
    }
    
    # Create SHA256 hash of complete verification evidence
    hash_object = hashlib.sha256(json.dumps(combined_data, sort_keys=True).encode('utf-8'))
    evidence_hash = hash_object.hexdigest()
    
    return evidence_hash
```

---

## Task 7: Rust Enclave Integration
**File**: Rust enclave codebase

### Requirements:
1. **Consume Redis verification requests**
2. **Call government APIs within enclave**
3. **Generate evidence hash from complete verification**
4. **Sign verification result in enclave**

### Rust Implementation Structure:
```rust
pub struct VerificationRequest {
    user_wallet: String,
    did_id: String,
    verification_type: String,
    document_data: serde_json::Value,
    ocr_hash: String,
}

pub struct VerificationResult {
    request: VerificationRequest,
    gov_api_response: serde_json::Value,
    evidence_hash: String,
    signature: String,
    verified_at: String,
}

impl VerificationProcessor {
    async fn process_verification(&self, request: VerificationRequest) -> VerificationResult {
        // 1. Call government API within enclave
        // 2. Generate evidence hash from request + response
        // 3. Sign the evidence hash
        // 4. Return complete verification result
    }
}
```

---

## Task 8: Database Schema Updates
**File**: Database migration

### New Fields Required:
```sql
-- Add to user_verification table
ALTER TABLE user_verification ADD COLUMN government_api_response JSONB;
ALTER TABLE user_verification ADD COLUMN verification_evidence_hash VARCHAR(255);
ALTER TABLE user_verification ADD COLUMN enclave_signature VARCHAR(255);
ALTER TABLE user_verification ADD COLUMN actual_verification_status VARCHAR(50) DEFAULT 'pending';

-- Update is_verified logic to check actual_verification_status
```

---

## Task 9: Frontend Updates
**Files**: Frontend correction flow

### Requirements:
1. **Add data correction interface**
2. **Show verification status as "pending" initially**
3. **Update UI based on actual verification results**

### New Flow:
```
OCR Results → User Correction → Confirm Data → Send for Verification → Wait for Result
```

---

## Task 10: Error Handling & Monitoring
**Files**: All services

### Requirements:
1. **Handle government API failures**
2. **Retry logic for API calls**  
3. **Monitoring for verification success/failure rates**
4. **Webhook for enclave verification results**

---

## Implementation Priority:

### Phase 1 (Critical):
- Task 1: Authentication Service
- Task 2: Government Verification Service  
- Task 3: Redis Stream Updates

### Phase 2 (Core):
- Task 4: KYC Router Updates
- Task 5: OTP Router Updates
- Task 6: Evidence Hash Updates

### Phase 3 (Integration):
- Task 7: Rust Enclave Updates
- Task 8: Database Schema Updates

### Phase 4 (UX):
- Task 9: Frontend Updates
- Task 10: Error Handling & Monitoring

This architecture ensures actual verification happens in the secure enclave environment with real government API responses, creating truly verifiable evidence hashes.