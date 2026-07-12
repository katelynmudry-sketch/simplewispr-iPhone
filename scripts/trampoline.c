#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    const char *home = getenv("HOME");
    if (!home) {
        fprintf(stderr, "MyWispr: HOME is not set\n");
        return 1;
    }

    const char *suffix = "/Library/Application Support/MyWispr/app/scripts/run.sh";
    size_t len = strlen(home) + strlen(suffix) + 1;
    char *run_sh = malloc(len);
    if (!run_sh) {
        fprintf(stderr, "MyWispr: malloc failed\n");
        return 1;
    }
    snprintf(run_sh, len, "%s%s", home, suffix);

    if (access(run_sh, F_OK) != 0) {
        fprintf(stderr, "MyWispr: run.sh not found at %s\n", run_sh);
        free(run_sh);
        return 1;
    }

    /* Forward all original args: {"bash", run_sh, argv[1], ..., argv[argc-1], NULL} */
    char **new_argv = malloc((size_t)(argc + 2) * sizeof(char *));
    if (!new_argv) {
        fprintf(stderr, "MyWispr: malloc failed\n");
        free(run_sh);
        return 1;
    }
    new_argv[0] = "bash";
    new_argv[1] = run_sh;
    for (int i = 1; i < argc; i++) {
        new_argv[i + 1] = argv[i];
    }
    new_argv[argc + 1] = NULL;

    execv("/bin/bash", new_argv);
    perror("MyWispr: execv");
    return 1;
}
