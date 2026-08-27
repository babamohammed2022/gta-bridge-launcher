-- gta_bridge ASI - minimal MMO-style agent for GTA SA
solution "gta_bridge"
    configurations { "Release", "Debug" }
    platforms { "Win32" }
    location "build"
    targetdir "bin"
    implibdir "bin"

    staticruntime "On"
    rtti "Off"
    useimportlib "Off"
    buffersecuritycheck "Off"

    defines { "_CRT_SECURE_NO_WARNINGS", "_SCL_SECURE_NO_WARNINGS" }

    includedirs {
        "src",
        "src/shared",
        "src/shared/injector",
        "src/shared/structs",
    }

    filter "configurations:Debug*"
        symbols "On"
    filter "configurations:Release*"
        defines { "NDEBUG" }
        optimize "Speed"
    filter "action:vs*"
        buildoptions { "/arch:IA32" }
    filter {}

    project "gta_bridge"
        language "C++"
        kind "SharedLib"
        targetname "gta_bridge"
        targetextension ".asi"
        files {
            "src/bridge.cpp",
            "src/shared/injector/**.hpp",
            "src/shared/injector/**.h",
            "src/shared/structs/**.h",
        }
