# Day 12: Threshold Tuning & Legitimate Browsing Calibration Engine
import json

class LegitimateVelocityCalibrator:
    def __init__(self):
        # Baseline limits established in earlier structural models
        self.base_max_requests = 100
        
        # Calibrated scaling constants optimized for modern web browsers
        self.multi_tab_multiplier = 2.5   
        self.bulk_read_multiplier = 1.8   

    def calibrate_and_evaluate(self, session_context, current_request_count):
        """
        Day 12 Target: Tune sensitivity thresholds so legitimate multi-tab navigation 
        and bulk read operations do not trigger false alerts.
        """
        is_multi_tab = session_context.get("is_multi_tab_active", False)
        is_bulk_read = session_context.get("is_bulk_read_operation", False)
        
        # Calculate dynamic threshold thresholds based on active behavioral indicators
        calibrated_threshold = self.base_max_requests
        if is_multi_tab:
            calibrated_threshold *= self.multi_tab_multiplier
        if is_bulk_read:
            calibrated_threshold *= self.bulk_read_multiplier

        # Process telemetry boundary assertions
        if current_request_count > calibrated_threshold:
            return {
                "is_false_positive": False,
                "status": "VALID_ANOMALY_TRIGGERED",
                "calibrated_threshold_used": calibrated_threshold,
                "action": "BLOCK"
            }
            
        return {
            "is_false_positive": True,
            "status": "LEGITIMATE_CALIBRATED_TRAFFIC_SUPPRESSED",
            "calibrated_threshold_used": calibrated_threshold,
            "action": "ALLOW"
        }

if __name__ == "__main__":
    calibrator = LegitimateVelocityCalibrator()
    
    # Simulate user opening multiple tabs simultaneously generating a rapid burst of 150 requests
    mock_user_context = {"is_multi_tab_active": True, "is_bulk_read_operation": False}
    user_requests = 150
    
    assessment = calibrator.calibrate_and_evaluate(mock_user_context, user_requests)
    print("Executing Day 12 Calibration Output:\n", json.dumps(assessment, indent=4))
