TYPE
	MotorStateEnum : (
		MOTORSTATE_IDLE,
		MOTORSTATE_STARTING,
		MOTORSTATE_RUNNING,
		MOTORSTATE_STOPPING,
		MOTORSTATE_FAULT
	);
	MotorConfigType : STRUCT
		MaxSpeed    : REAL := 3000.0;  (* Maximum motor speed [rpm] *)
		RampTime    : TIME := T#2s;    (* Acceleration ramp time *)
		FaultLimit  : REAL := 3500.0;  (* Overspeed fault threshold [rpm] *)
	END_STRUCT;
END_TYPE
