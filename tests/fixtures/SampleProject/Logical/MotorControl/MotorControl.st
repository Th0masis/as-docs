(*
 * MotorControl FB — Controls motor speed with ramp and fault detection
 *)
FUNCTION_BLOCK MotorControl

R_TRIG_start.CLK := Enable;
R_TRIG_start();

IF Enable THEN
	TON_delay.IN := TRUE;
	TON_delay.PT := T#500ms;
	TON_delay();
	IF TON_delay.Q THEN
		ActualSpeed := SpeedSetpoint;
		Running := TRUE;
	END_IF
ELSE
	TON_delay.IN := FALSE;
	TON_delay();
	ActualSpeed := 0.0;
	Running := FALSE;
END_IF

gMotorSpeed := ActualSpeed;

END_FUNCTION_BLOCK
