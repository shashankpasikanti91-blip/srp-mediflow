"""
KIE AI Integration - Speech to Text with ElevenLabs
Better speech recognition for the hospital chatbot
"""

import requests
import json
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv('KIE_API_KEY', 'd0af5597f5b6d84865996e949409aaa0')
API_URL = "https://api.kie.ai/api/v1/jobs/createTask"
STATUS_URL = "https://api.kie.ai/api/v1/jobs/getStatus"

def transcribe_audio(audio_url, language_code='en', diarize=False):
    """
    Transcribe audio using KIE AI ElevenLabs Speech-to-Text API
    
    Supports 99 languages including:
    - English: en
    - Telugu: te
    - Hindi: hi
    - Tamil: ta
    - Kannada: kn
    - Malayalam: ml
    
    Returns: Transcribed text
    """
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "model": "elevenlabs/speech-to-text",
        "input": {
            "audio_url": audio_url,
            "language_code": language_code,
            "tag_audio_events": True,
            "diarize": diarize
        }
    }
    
    try:
        print(f"Sending transcription request for {language_code}...")
        response = requests.post(API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('jobId')
            print(f"Job created: {job_id}")
            
            # Poll for result
            return poll_result(job_id, headers)
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error in transcription: {e}")
        return None

def poll_result(job_id, headers, max_attempts=30):
    """Poll for transcription result"""
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(
                f"{STATUS_URL}?jobId={job_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'completed':
                    return result.get('output', {}).get('text', '')
                elif result.get('status') == 'failed':
                    print("Transcription failed")
                    return None
                    
                # Still processing
                print(f"Processing... (attempt {attempt + 1}/{max_attempts})")
                time.sleep(2)
            else:
                print(f"Error checking status: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error polling result: {e}")
            return None
    
    print("Timeout waiting for transcription")
    return None

def detect_language_from_audio(audio_url):
    """
    Detect language from audio (uses English first, can be enhanced)
    Returns language code: 'en', 'te', 'hi', etc.
    """
    # Try with automatic language detection
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "model": "elevenlabs/speech-to-text",
        "input": {
            "audio_url": audio_url,
            # No language_code = auto-detect
            "tag_audio_events": True
        }
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            result = response.json()
            job_id = result.get('jobId')
            
            # Poll for result
            result = poll_result(job_id, headers)
            
            # Detect language from result metadata (if available)
            # For now, return 'en' as default
            return 'en'
    except:
        return 'en'

# Example usage
if __name__ == "__main__":
    # Test with a sample audio
    audio_url = "https://file.aiquickdraw.com/custom-page/akr/section-images/1757157053357tn37vxc8.mp3"
    
    result = transcribe_audio(audio_url, language_code='en')
    print(f"Transcription result: {result}")
