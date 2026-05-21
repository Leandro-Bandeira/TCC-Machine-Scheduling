from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    id: int
    order_id: int
    resource_id: int
    processing_slots: int
    release_date_slot: int
    due_date_slot: int

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        return cls(
            id=data["id"],
            order_id=data["order_id"],
            resource_id=data["resource_id"],
            processing_slots=data["processing_slots"],
            release_date_slot=data["release_date_slot"],
            due_date_slot=data["due_date_slot"],
        )


@dataclass(frozen=True)
class Machine:
    id: int
    machine_name: str
    job_capacity: int
    start_slots: list[int]

    @classmethod
    def from_dict(cls, data: dict) -> "Machine":
        return cls(
            id=data["machine_id"],
            machine_name=data["machine_name"],
            job_capacity=data["job_capacity"],
            start_slots=data["start_slots"],
        )
