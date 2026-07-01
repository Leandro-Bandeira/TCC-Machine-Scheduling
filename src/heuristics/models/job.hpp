#pragma once

// Representa um job (ordem de produção) a ser sequenciado na máquina.
// Todos os tempos são expressos em slots (unidade discreta de tempo do modelo).
class Job{
    public:
        int id;               // Identificador original do job no JSON de entrada
        int processing_slots; // Duração de processamento em slots
        int release_date_slot;// Slot mais cedo em que o job pode iniciar (data de liberação)
        int due_date_slot;    // Slot de vencimento — atrasos além deste geram tardiness
        int resource_id;      // Tipo de recurso/família do job (usado para calcular setup)
        int idx;              // Índice interno na matriz de setup (0 = dummy job)

        Job(int id, int processing_slots, int release_date_slot, int due_date_slot, int resource_id, int idx)
            : id(id), processing_slots(processing_slots), release_date_slot(release_date_slot), due_date_slot(due_date_slot), resource_id(resource_id), idx(idx) {}
};
