/* Login shell for SSH accounts. The player and every child inherit the filter. */
#include <errno.h>
#include <seccomp.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static int local_sockets_only(void) {
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);
    if (!ctx) return -1;
    const unsigned deny = SCMP_ACT_ERRNO(EPERM);
    int rc = seccomp_rule_add(ctx, deny, SCMP_SYS(socket), 1,
                              SCMP_A0(SCMP_CMP_NE, AF_UNIX));
    if (!rc) rc = seccomp_rule_add(ctx, deny, SCMP_SYS(socketpair), 1,
                                  SCMP_A0(SCMP_CMP_NE, AF_UNIX));
    if (!rc) rc = seccomp_rule_add(ctx, deny, SCMP_SYS(io_uring_setup), 0);
    if (!rc) rc = seccomp_rule_add(ctx, deny, SCMP_SYS(io_uring_enter), 0);
    if (!rc) rc = seccomp_rule_add(ctx, deny, SCMP_SYS(io_uring_register), 0);
    if (!rc) rc = seccomp_load(ctx);
    seccomp_release(ctx);
    return rc;
}

int main(void) {
    char role[24];
    FILE *file = fopen("/run/frost/role", "r");
    if (!file || !fgets(role, sizeof(role), file)) return 1;
    fclose(file);
    if (strcmp(role,"player\n")==0) {
        if (local_sockets_only()!=0) {
            fputs("Spieler-Isolation konnte nicht aktiviert werden.\n", stderr);
            return 1;
        }
    } else if (strcmp(role,"gateway\n") && strcmp(role,"scoreboard\n")) {
        return 1;
    }
    execl("/usr/bin/python3","python3","-I","-m","frost.login",(char *)NULL);
    return 1;
}
