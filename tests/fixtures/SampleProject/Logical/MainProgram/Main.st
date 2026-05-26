(*
 * MainProgram — Main cyclic program
 * Coordinates motor start/stop sequence using a state machine.
 *)

(* _INIT section *)
State := MOTORSTATE_IDLE;
gMotorSpeed := 0.0;
gFault := FALSE;

(* _CYCLIC section *)
CASE State OF

	MOTORSTATE_IDLE:
		gMotorSpeed := 0.0;
		IF StartCmd AND NOT gFault THEN
			State := MOTORSTATE_STARTING;
			TON_ramp.PT := Config.RampTime;
			TON_ramp.IN := TRUE;
			TON_ramp();
		END_IF

	MOTORSTATE_STARTING:
		TON_ramp.IN := TRUE;
		TON_ramp();
		gMotorSpeed := gMotorSpeed + 100.0;
		IF gMotorSpeed >= Config.MaxSpeed THEN
			gMotorSpeed := Config.MaxSpeed;
			State := MOTORSTATE_RUNNING;
		END_IF
		IF gMotorSpeed > Config.FaultLimit THEN
			gFault := TRUE;
			State := MOTORSTATE_FAULT;
		END_IF

	MOTORSTATE_RUNNING:
		IF StopCmd THEN
			State := MOTORSTATE_STOPPING;
			TON_ramp.IN := FALSE;
			TON_ramp();
		END_IF
		IF gMotorSpeed > Config.FaultLimit THEN
			gFault := TRUE;
			State := MOTORSTATE_FAULT;
		END_IF

	MOTORSTATE_STOPPING:
		gMotorSpeed := gMotorSpeed - 100.0;
		IF gMotorSpeed <= 0.0 THEN
			gMotorSpeed := 0.0;
			State := MOTORSTATE_IDLE;
		END_IF

	MOTORSTATE_FAULT:
		gMotorSpeed := 0.0;
		TON_ramp.IN := FALSE;
		TON_ramp();
		IF NOT gFault THEN
			State := MOTORSTATE_IDLE;
		END_IF

END_CASE

gCycleCount := gCycleCount + 1;
