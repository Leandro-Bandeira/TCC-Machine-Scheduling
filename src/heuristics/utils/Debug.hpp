#ifndef DEBUG_H
#define DEBUG_H

#include <iostream>
#include <fstream>
#include <string>
#include <iomanip>
#include <mutex>
#include "params.hpp"
class Debug {
private:
    std::ofstream arquivo;
    std::mutex mtx; // Garante que a escrita seja segura para múltiplas threads

    // Construtor PRIVADO: abre o arquivo na primeira utilização do agente
    Debug() {
        arquivo.open("execucao_debug.txt", std::ios::app);
        if (arquivo.is_open()) {
            arquivo << std::fixed << std::setprecision(10);
            arquivo << "=== INÍCIO DA SESSÃO DE DEBUG ===\n";
        }
    }

    // Destrutor PRIVADO: fecha o arquivo automaticamente no encerramento do programa
    ~Debug() {
        if (arquivo.is_open()) {
            arquivo << "=== FIM DA SESSÃO DE DEBUG ===\n\n";
            arquivo.close();
        }
    }

    // Retorna a referência estática única (Meyers Singleton - Thread-Safe desde o C++11)
    static Debug& instance() {
        static Debug agente; // Criado apenas 1 vez, no primeiro uso!
        return agente;
    }

public:
    // Impede cópias e atribuições
    Debug(const Debug&) = delete;
    void operator=(const Debug&) = delete;
    // Sobrecarga para mensagens de texto simples
    static void log(const std::string& mensagem) {
        if (!writeDebugFiles){
            return;
        }
        Debug& dbg = instance();
        std::lock_guard<std::mutex> lock(dbg.mtx);

        if (dbg.arquivo.is_open()) {
            dbg.arquivo << "----------------------------------" << "\n";
            dbg.arquivo << mensagem << "\n";
            dbg.arquivo << "----------------------------------" << "\n";
            dbg.arquivo.flush();
        }
    }
};

#endif