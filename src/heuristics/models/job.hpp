#pragma once


class Job{
    public:
        int id;
        int processing_slots;
        int release_date_slot;
        int due_date_slot;
        int resource_id;
        int idx;

        Job(int id, int processing_slots, int release_date_slot, int due_date_slot, int resource_id, int idx)
            : id(id), processing_slots(processing_slots), release_date_slot(release_date_slot), due_date_slot(due_date_slot), resource_id(resource_id), idx(idx) {}
};
