
> note: the article may contain errors, of spellings, codes, or others... 
> if you find one do not hesitate to make an issue or a pr to [github.com/supercip971/supercip971.github.io](https://github.com/Supercip971/supercip971.github.io) <3


## What is a syscall?

Syscalls allow to execute kernel actions from userspace. They are like complex *functions* that link the program and the kernel.
For example we can have a syscall to allocate memory, one to open a file... This is an important part of the kernel that needs to be very fast because a user applications can call a lot of syscalls.  

## What were we doing before for syscalls?

Before (and some are still using it, and it's still quite effective) we used the interrupts of the cpu: the interrupt allows you to go directly to the kernel by executing specific code pointed in the interrupt table. 
The `int` instruction allows to call a certain interrupt, for exemple we can use `int 68` for calling interrupts number 67. 
Some os reserve an interruption for the syscall (wingos used interrupt 127, linux use 128...) this interrupt may be the only interrupt that a RING 3 process can call. In the interrupt handler the registers are saved and used as arguments for the syscall. 

> note: all registers can be used, but RCX and R11 should not be used (if we want to easily make the kernel portable to 64bit syscall/sysret) because they are needed to save the cpu state with the `syscall` instruction

After the execution of the syscall code in the interrupt, we can modify the value of the RAX register so that it contains the syscall return value.

However interruptions are slow for syscall. It needs to check a lot of things and it's not the best solution available.

## Before syscall & sysret: sysenter & sysexit


Sysenter and Sysexit were added by intel.
One problem of sysenter and sysexit in 32Bit is that we don't know if it is supported. The instruction may not be available.
Another problem of sysenter is that you must write for each syscall the return address to RDX and the return stack to RCX, that's fine but you don't know what the RIP and RSP of the syscall is! 

The user app must put a return address and a return stack to syscall parameters themselves:

```nasm
sysenter_is_bad_imo:
    mov rcx, return_addr
    mov rsi, rsp
    mov rax, 0x28 ; just use a random syscall id
    sysenter

return_addr:
    ret
```

I think it is sketchy and can be the cause of error. This is my opinion, but I think syscall/sysret are 100 times better than sysenter/sysexit.


## What are syscall & sysret?

First what are syscall & sysret? 

Syscall and sysret are long mode instruction for doing syscall from userspace to the kernel.
These instructions allow you to make faster and safer syscalls.
They are faster thanks to the fact that it takes into account that it has consistent segments.

### Faster certainly but what is the gain in performance? 

I wanted to test on *GNU/* linux the syscall "Getpid", with an interrupt and with the syscall instruction (using g++ -O3, and google benchmarks)

source code:
```c++
#include <benchmark/benchmark.h>
#include <unistd.h>
static void get_pid_syscall_benchmark(benchmark::State& state) {
    for (auto _ : state) {
        asm volatile( "syscall\n"::"a"(0x27));
    }
}
BENCHMARK(get_pid_syscall_benchmark);

static void get_pid_interrupt_benchmark(benchmark::State& state) {
    for (auto _ : state) {
        asm volatile("int $128 \n"::"a"(0x27));
    }
}
BENCHMARK(get_pid_interrupt_benchmark);

BENCHMARK_MAIN();
```

__here are the results:__


| Benchmark                   | Time/CPU |
| --------------------------- | -------- |
| get_pid_syscall_benchmark   | 62.7 ns  |
| get_pid_interrupt_benchmark | 132 ns   |

the syscall is 2 times faster than the interrupt!

note: I have a ryzen 5 3600X so results can be different on other cpus and systems

however setting up a syscall is a bit more complicated than setting up a syscall with an interrupt:

first you need to turn them on with model specific register (address 0xC0000080 bit 0)

then you need to setup syscall gdt segments:

```c++
x86_wrmsr(STAR, ((uint64_t)SELECTOR_1 << 32) | ((uint64_t)(SELECTOR_2 | 3) << 48));
```

it is necessary to know that the MSR STAR register must contain the segment when the syscall is executed (ring 0) and the segment when the syscall is exited (ring 3) but it is also important that the gdt entry has a precise order:

- SELECTOR_1        : must be kernel code
- SELECTOR_1 + 8    : must be kernel data
- SELECTOR_2 + 8    : must be user data
- SELECTOR_2 + 16   : must be user code

So in wingos I changed the order of the gdt to have:
- 0     null_segment
- 8     kernel_code
- 16    kernel_data
- 24    user_data
- 32    user_code

I can have SELECTOR_1 = kernel code
and SELECTOR_2 = kernel data | 3

It's maybe weird but it's one of the only solution I found except if I make an empty entry between KERNEL_DATA and USER_DATA.

Then you have to load the address of the syscall handler in the LSTAR register.

#### __The syscall handler__:

Before talking about the syscall handler I should tell you that in 64bit and with smp, there is a local structure for each cpu stored in the gs register (other kernels can use fs). This structure contains a temporary stack for the syscall, an address to store the process stack temporarily (and maybe other things...). 


the local cpu structure stored in gs:
```c++
class cpu
{
public:
    uint8_t *syscall_stack; // the stack for the syscall
    uint64_t saved_stack; // an address for saving the current process stack
    // ... other data like cpu id, current idt tss and other value
};
```

So at each syscall we change the stack temporarily to use the syscall_stack.

But in 64bit a user can write to the gs register (with `wrgsbase`)! which can really be problematic... So we use the instruction:

```nasm
swapgs
``` 

Which allows to change between user gs and the gs which is stored in the msr register: `KERNEL_GS` so we can 'secure' the use of the gs register. At the end of the syscall_handle we can call swapgs again to reset to the previous value of gs. 

Also when entering the syscall_handle, the cpu puts the previous value of RIP in RCX and the previous value of RFLAGS in R11. The processor also uses them to reset the value of RIP and RFLAGS when the syscall returns.

Here is my sycall handler:

```nasm
syscall_handle:
    swapgs
    mov [gs:0x8], rsp       ; gs.saved_stack = rsp
    mov rsp, [gs:0x0]       ; rsp = gs.syscall_stack 

    ; push information (gs, cs, rip, rflags, rip...)
    push qword 0x1b         ; user data segment
    push qword [gs:0x8]     ; saved stack
    push r11                ; saved rflags
    push qword 0x23         ; user code segment 
    push rcx                ; current RIP

    push_all                ; push every register

    mov rdi, rsp            ; put the stackframe as the syscall argument
    mov rbp, 0
    call syscall_higher_handler ; jump to beautiful higher level code

    pop_all_syscall         ; pop every register except RAX as we use it for the return value

    mov rsp, [gs:0x8]
    swapgs
    sti
    o64 sysret
```

We should not pop the rax register because we want to keep its value.

Then the syscall_higher_handler manages which syscall to call from the rax register (which stores the syscall id).

### How userspace call the syscall?

It's like interrupt but we replace `int $127` with `syscall`.
We also need to change the asm code to push and pop R11 and RCX registers, because they keep their values (RCX for RIP and R11 for RFLAGS).

```c++
inline uint64_t syscall(uint64_t syscall_id, uint64_t arg1, uint64_t arg2, uint64_t arg3, uint64_t arg4)
{
    uint64_t syscall_return = 0;
    asm volatile(
        "push r11 \n"
        "push rcx \n"
        "syscall \n"
        "pop rcx \n"
        "pop r11 \n"
        : "=a"(syscall_return)
        : "a"(syscall_id), "b"(arg1), "d"(arg2), "S"(arg3), "D"(arg4)
        : "memory");
    return syscall_return;
}
```

Et voila! This was how syscall/sysret was implemented in wingos!
